"""Paimon-backed lineage repository — audit trail & time-travel from Paimon gold via pypaimon."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from repositories.base import AbstractLineageRepository

logger = logging.getLogger(__name__)

MCP_SYNC_URL = "http://localhost:8084"


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


class PaimonLineageRepository(AbstractLineageRepository):
    """Audit trail and time-travel backed by Paimon gold tables via pypaimon direct reads."""

    def __init__(self, paimon_client, sync_base_url: str = MCP_SYNC_URL,
                 flink_client=None):
        self._paimon = paimon_client
        self._sync_url = sync_base_url
        self._flink = flink_client  # kept for write operations (restore)

    def get_entities_with_audit(self) -> list[dict]:
        rows = self._paimon.read_table(
            "gold.resolution_audit",
            columns=["target_golden_id"],
        )

        if not rows:
            return []

        gids = list({r.get("target_golden_id") for r in rows if r.get("target_golden_id")})
        if not gids:
            return []

        # Fetch entity names from golden_records
        gr_rows = self._paimon.read_table(
            "gold.golden_records",
            columns=["golden_record_id", "canonical_name", "naics_code", "status"],
        )
        gr_map = {r["golden_record_id"]: r for r in gr_rows if r.get("status") != "PROVISIONAL"}

        results = []
        for gid in gids:
            gr = gr_map.get(gid)
            if gr:
                results.append({
                    "id": gr.get("golden_record_id"),
                    "name": gr.get("canonical_name"),
                    "industry": gr.get("naics_code"),
                    "status": gr.get("status"),
                })
        results.sort(key=lambda x: x.get("name") or "")
        return results

    def get_audit_trail(self, entity_id: str, limit: int = 100) -> list[dict]:
        rows = self._paimon.read_table("gold.resolution_audit")

        # Filter for this entity
        filtered = [
            r for r in rows
            if r.get("target_golden_id") == entity_id or r.get("absorbed_golden_id") == entity_id
        ]

        # Sort by created_at ASC
        filtered.sort(key=lambda r: str(r.get("created_at") or ""))

        # Limit
        filtered = filtered[:limit]

        json_cols = ("dimension_scores", "key_factors", "evaluation_chain",
                     "golden_record_before", "golden_record_after")
        result = []
        for r in filtered:
            entry = dict(r)
            for col in json_cols:
                if col in entry:
                    entry[col] = _parse_json(entry[col])
            # Serialize timestamps
            for key in ("created_at",):
                val = entry.get(key)
                if val and hasattr(val, "isoformat"):
                    entry[key] = val.isoformat()
                elif val:
                    entry[key] = str(val)
            entry["entity_id"] = entity_id
            result.append(entry)
        return result

    def get_snapshot(self, entity_id: str, date: str) -> Optional[dict]:
        rows = self._paimon.read_table("gold.resolution_audit")

        # Filter for this entity, before the given date
        filtered = [
            r for r in rows
            if (r.get("target_golden_id") == entity_id or r.get("absorbed_golden_id") == entity_id)
            and str(r.get("created_at") or "") <= date
        ]

        if not filtered:
            return None

        # Sort desc by created_at, take latest
        filtered.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return _parse_json(filtered[0].get("golden_record_after"))

    def restore(self, entity_id: str, snapshot: dict, audit_id: str) -> dict:
        # Restore still needs Flink SQL for writes (if available)
        if not self._flink or not self._flink.available:
            return {"success": False, "error": "Flink SQL Gateway required for writes"}

        try:
            import datetime as dt
            now_ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            self._flink.execute_update(
                "INSERT INTO gold.golden_records "
                "(golden_record_id, canonical_name, confidence, status, persona, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, TIMESTAMP %s)",
                [
                    entity_id,
                    snapshot.get("canonical_name"),
                    snapshot.get("confidence", 0),
                    "ACTIVE",
                    json.dumps(snapshot.get("persona", {}), default=str),
                    now_ts,
                ],
            )

            new_audit_id = f"A-{uuid.uuid4().hex[:8]}"
            self._flink.execute_update(
                "INSERT INTO gold.resolution_audit "
                "(audit_id, event_id, record_id, perspective, decision, trigger_type, "
                "target_golden_id, confidence, reasoning, golden_record_after, created_at) "
                "VALUES (%s, %s, %s, 'GLOBAL', 'RESTORE', 'USER_ACTION', %s, %s, %s, %s, TIMESTAMP %s)",
                [
                    new_audit_id,
                    f"restore-{audit_id}",
                    entity_id,
                    entity_id,
                    snapshot.get("confidence", 0),
                    f"User restored entity to state from audit {audit_id}",
                    json.dumps(snapshot, default=str),
                    now_ts,
                ],
            )

            self._sync_golden_record(snapshot | {"golden_record_id": entity_id})
            return {"success": True, "audit_id": new_audit_id}

        except Exception as e:
            logger.error(f"Restore failed for {entity_id}: {e}")
            return {"success": False, "error": str(e)}

    def _sync_golden_record(self, data: dict):
        try:
            import httpx
            httpx.post(f"{self._sync_url}/sync/golden-record", json=data, timeout=5.0)
        except Exception as e:
            logger.warning(f"Neo4j sync failed (non-fatal): {e}")
