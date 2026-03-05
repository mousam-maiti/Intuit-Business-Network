"""Paimon-backed resolution repository — reads and writes via pypaimon (no Flink SQL Gateway)."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from repositories.base import AbstractResolutionRepository

logger = logging.getLogger(__name__)

MCP_SYNC_URL = "http://localhost:8084"


def _time_ago(dt) -> str:
    if not dt:
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except (ValueError, TypeError):
            return dt
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        m = seconds // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if seconds < 86400:
        h = seconds // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = seconds // 86400
    if d < 7:
        return f"{d} day{'s' if d != 1 else ''} ago"
    w = d // 7
    return f"{w} week{'s' if w != 1 else ''} ago"


def _parse_json(val):
    if val is None:
        return None
    if isinstance(val, (list, dict)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val


class PaimonResolutionRepository(AbstractResolutionRepository):
    """Pending resolution backed by Paimon gold.pending_resolution via pypaimon reads + writes."""

    def __init__(self, paimon_client, flink_client=None, sync_base_url: str = MCP_SYNC_URL):
        self._paimon = paimon_client
        self._flink = flink_client
        self._sync_url = sync_base_url

    def get_pending(self, neo4j_client=None, relationship_client=None) -> list[dict]:
        all_rows = self._paimon.read_table("gold.pending_resolution")
        # Deduplicate by match_id: if a record was resolved (MERGED/REJECTED) but a
        # stale PENDING row also exists, prefer the resolved status.
        by_match = {}
        for r in all_rows:
            mid = r.get("match_id")
            if mid not in by_match:
                by_match[mid] = r
            elif r.get("status") != "PENDING":
                by_match[mid] = r  # resolved status wins
        rows = [r for r in by_match.values() if r.get("status") == "PENDING"]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)

        # Pre-load golden records from Paimon for fallback when Neo4j doesn't have the entity
        # Prefer rows with a canonical_name (duplicates can exist from partial-write bugs)
        gr_lookup = {}
        all_grs = self._paimon.read_table("gold.golden_records")
        for gr in all_grs:
            gid = gr.get("golden_record_id")
            if gid:
                existing = gr_lookup.get(gid)
                if not existing or (not existing.get("canonical_name") and gr.get("canonical_name")):
                    gr_lookup[gid] = gr

        results = []
        for pr in rows:
            orphan_entity = None
            candidate_entity = None
            oid = pr.get("orphan_golden_id")
            cid = pr.get("candidate_golden_id")

            if neo4j_client and hasattr(neo4j_client, 'available') and neo4j_client.available:
                if oid:
                    orphan_entity = neo4j_client.get_by_id(oid)
                if cid:
                    candidate_entity = neo4j_client.get_by_id(cid)

            # Fallback to Paimon golden_records if Neo4j didn't have the entity or returned empty name
            if (not orphan_entity or not (orphan_entity or {}).get("name")) and oid and oid in gr_lookup:
                gr = gr_lookup[oid]
                persona = _parse_json(gr.get("persona")) or {}
                loc = persona.get("location", {}) if isinstance(persona, dict) else {}
                ind = persona.get("industry", {}) if isinstance(persona, dict) else {}
                orphan_entity = {
                    "id": oid,
                    "name": gr.get("canonical_name") or "",
                    "naics": ind.get("original_category") or (f"NAICS {ind['naics_code']}" if ind.get("naics_code") else ""),
                    "city": loc.get("city_norm") or "",
                    "state": loc.get("state") or "",
                }
            if (not candidate_entity or not (candidate_entity or {}).get("name")) and cid and cid in gr_lookup:
                gr = gr_lookup[cid]
                candidate_entity = {"id": cid, "name": gr.get("canonical_name") or ""}

            dim_scores = _parse_json(pr.get("dimension_scores")) or {}
            if "identity" in dim_scores:
                dim_scores["name"] = dim_scores.pop("identity")

            orphan_city = (orphan_entity or {}).get("city", "")
            orphan_state = (orphan_entity or {}).get("state", "")
            location = f"{orphan_city}, {orphan_state}".strip(", ")

            shared = []
            if relationship_client and hasattr(relationship_client, 'available') and relationship_client.available and oid and cid:
                shared = relationship_client.get_common_neighbors(oid, cid).get("common_neighbors", [])
                shared = [n.get("name", "") for n in shared[:5]]

            results.append({
                "id": pr.get("match_id"),
                "inputName": (orphan_entity or {}).get("name"),
                "inputCategory": (orphan_entity or {}).get("naics"),
                "inputLocation": location or None,
                "candidate": candidate_entity,
                "confidence": float(pr["confidence"]) if pr.get("confidence") is not None else None,
                "age": _time_ago(pr.get("created_at")),
                "scores": dim_scores,
                "sharedNeighbors": shared,
                "triggerType": pr.get("trigger_type", "AI_AGENT"),
            })
        return results

    def get_orphan_golden_id(self, match_id: str):
        """Return the orphan_golden_id for a given match_id."""
        rows = self._paimon.query(
            "gold.pending_resolution",
            columns=["match_id", "orphan_golden_id"],
            filters={"match_id": match_id},
        )
        return rows[0]["orphan_golden_id"] if rows else None

    def resolve(self, match_id: str, resolution: str, candidate_override_id: str = None) -> dict:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        now_ts = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        if resolution == "accept":
            return self._execute_accepted_merge(match_id, now_ts, now_iso, candidate_override_id=candidate_override_id)

        # ── Reject path ──
        pending_rows = self._paimon.query(
            "gold.pending_resolution", filters={"match_id": match_id},
        )
        if not pending_rows:
            raise ValueError(f"Pending resolution {match_id} not found")
        pr = pending_rows[0]
        orphan_id = pr.get("orphan_golden_id")

        # Write back full record with REJECTED status (Paimon upsert replaces entire row)
        pr["status"] = "REJECTED"
        pr["reviewer"] = "user"
        pr["reviewed_at"] = now_ts
        self._paimon.write_row("gold.pending_resolution", pr)

        # Promote orphan to standalone ACTIVE entity (reject = create new entity)
        if orphan_id:
            # Read full record so we can write it back complete (Paimon upsert replaces entire row)
            orphan_rows = self._paimon.query(
                "gold.golden_records", filters={"golden_record_id": orphan_id}
            )
            if orphan_rows:
                full_record = orphan_rows[0]
                full_record["status"] = "ACTIVE"
                full_record["entity_type"] = "GOLDEN"
                full_record["updated_at"] = now_ts
                self._paimon.write_row("gold.golden_records", full_record)
                # Sync full record to Neo4j so it appears in search/network
                self._sync_golden_record_full(full_record)

        return {"matchId": match_id, "resolution": resolution, "resolvedAt": now_iso}

    def _execute_accepted_merge(self, match_id: str, now_ts: str, now_iso: str, candidate_override_id: str = None) -> dict:
        # Get pending resolution via pypaimon
        pending_rows = self._paimon.query(
            "gold.pending_resolution", filters={"match_id": match_id}
        )
        if not pending_rows:
            raise ValueError(f"Pending resolution {match_id} not found")
        pr = pending_rows[0]

        orphan_id = pr["orphan_golden_id"]
        candidate_id = candidate_override_id or pr["candidate_golden_id"]

        # Get golden records via pypaimon
        orphan_rows = self._paimon.query(
            "gold.golden_records", filters={"golden_record_id": orphan_id}
        )
        candidate_rows = self._paimon.query(
            "gold.golden_records", filters={"golden_record_id": candidate_id}
        )
        if not orphan_rows or not candidate_rows:
            raise ValueError(f"Golden record(s) not found: orphan={orphan_id}, candidate={candidate_id}")

        orphan_gr = orphan_rows[0]
        candidate_gr = candidate_rows[0]

        orphan_variants = _parse_json(orphan_gr.get("name_variants")) or []
        candidate_variants = _parse_json(candidate_gr.get("name_variants")) or []
        merged_variants = list(set(candidate_variants) | set(orphan_variants))

        orphan_sources = _parse_json(orphan_gr.get("source_records")) or []
        candidate_sources = _parse_json(candidate_gr.get("source_records")) or []
        merged_sources = list(set(candidate_sources) | set(orphan_sources))

        new_source_count = len(merged_sources)
        old_confidence = float(candidate_gr["confidence"]) if candidate_gr.get("confidence") is not None else 0.5
        new_confidence = min(0.99, old_confidence + 0.05)

        # Update candidate golden record in Paimon (read-modify-write full row)
        candidate_gr["name_variants"] = json.dumps(merged_variants)
        candidate_gr["source_records"] = json.dumps(merged_sources)
        candidate_gr["source_count"] = new_source_count
        candidate_gr["confidence"] = new_confidence
        candidate_gr["status"] = "ACTIVE"
        candidate_gr["updated_at"] = now_ts
        self._paimon.write_row("gold.golden_records", candidate_gr)

        # Mark orphan as MERGED in Paimon (read-modify-write full row)
        orphan_gr["status"] = "MERGED"
        orphan_gr["merged_into"] = candidate_id
        orphan_gr["updated_at"] = now_ts
        self._paimon.write_row("gold.golden_records", orphan_gr)

        # Update pending_resolution status (read-modify-write full row)
        pr["candidate_golden_id"] = candidate_id
        pr["status"] = "MERGED"
        pr["reviewer"] = "user"
        pr["reviewed_at"] = now_ts
        self._paimon.write_row("gold.pending_resolution", pr)

        # Write audit record to Paimon
        audit_id = f"A-{uuid.uuid4().hex[:8]}"
        self._paimon.write_row("gold.resolution_audit", {
            "audit_id": audit_id,
            "event_id": f"user-accept-{match_id}",
            "record_id": orphan_id,
            "perspective": "GLOBAL",
            "decision": "MERGE",
            "trigger_type": pr.get("trigger_type", "AI_AGENT"),
            "target_golden_id": candidate_id,
            "absorbed_golden_id": orphan_id,
            "confidence": float(pr["confidence"]) if pr.get("confidence") is not None else 0.0,
            "reasoning": f"User accepted merge of {orphan_id} into {candidate_id}",
            "created_at": now_ts,
        })

        # Sync to Neo4j via MCP sync endpoints
        self._sync_golden_record({
            "golden_record_id": candidate_id,
            "name_variants": merged_variants,
            "source_records": merged_sources,
            "source_count": new_source_count,
            "confidence": new_confidence,
        })
        self._sync_golden_record({
            "golden_record_id": orphan_id,
            "status": "MERGED",
            "merged_into": candidate_id,
        })
        self._sync_audit({
            "audit_id": audit_id,
            "event_id": f"user-accept-{match_id}",
            "record_id": orphan_id,
            "perspective": "GLOBAL",
            "decision": "MERGE",
            "trigger_type": pr.get("trigger_type", "AI_AGENT"),
            "target_golden_id": candidate_id,
            "absorbed_golden_id": orphan_id,
            "confidence": float(pr["confidence"]) if pr.get("confidence") is not None else 0.0,
            "reasoning": f"User accepted merge of {orphan_id} into {candidate_id}",
        })

        logger.info(f"Accepted merge: {orphan_id} → {candidate_id} (match={match_id})")
        return {"matchId": match_id, "resolution": "accept", "resolvedAt": now_iso}

    def _sync_golden_record_full(self, record: dict):
        """Sync a full Paimon golden record to Neo4j, handling type serialization."""
        import math
        from decimal import Decimal as Dec
        data = {}
        for k, v in record.items():
            if v is None or (isinstance(v, float) and math.isnan(v)) or str(v) == "NaT":
                continue
            if isinstance(v, Dec):
                data[k] = float(v)
            elif hasattr(v, "isoformat"):
                data[k] = v.isoformat()
            elif isinstance(v, str):
                try:
                    data[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    data[k] = v
            else:
                data[k] = v
        self._sync_golden_record(data)

    def _sync_golden_record(self, data: dict):
        try:
            import httpx
            httpx.post(f"{self._sync_url}/sync/golden-record", json=data, timeout=5.0)
        except Exception as e:
            logger.warning(f"Neo4j sync failed (non-fatal): {e}")

    def _sync_audit(self, data: dict):
        try:
            import httpx
            httpx.post(f"{self._sync_url}/sync/audit", json=data, timeout=5.0)
        except Exception as e:
            logger.warning(f"Neo4j audit sync failed (non-fatal): {e}")
