"""
MySQL client for the REST API backend.

After the golden record migration to Neo4j (Phase 6), MySQL retains:
  - Source data: companies, bills, invoices, payments
  - Pending resolution: OLTP work queue for human review
  - Connections: auto_connections, manual_connections
  - Alerts: connection_alerts
  - Native overrides & merges: user customizations

Entity reads (golden_records), graph queries (relationships), audit trail,
and search now live in Neo4j (neo4j_client.py).
"""
from __future__ import annotations
import json
import logging
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from config import MySQLConfig

logger = logging.getLogger(__name__)

try:
    import mysql.connector
    from mysql.connector import pooling
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False


def _format_ein(raw: str | None) -> str | None:
    """Format EIN as XX-XXXXXXX."""
    if not raw:
        return None
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 9:
        return f"{digits[:2]}-{digits[2:]}"
    return raw


def _format_phone(raw: str | None) -> str | None:
    """Format phone as (XXX) XXX-XXXX."""
    if not raw:
        return None
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return raw


def _parse_json(val):
    """Safely parse a JSON string, returning the parsed value or the original."""
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


def _time_ago(dt) -> str:
    """Convert a datetime to a human-readable 'X ago' string."""
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


class MySQLClient:
    """MySQL client for source data, pending resolution, connections, alerts, and native features."""

    def __init__(self, cfg: MySQLConfig):
        self._cfg = cfg
        self._pool = None

    async def connect(self):
        if not HAS_MYSQL:
            raise RuntimeError("mysql-connector-python not installed")
        self._pool = pooling.MySQLConnectionPool(
            pool_name="be_pool",
            pool_size=self._cfg.pool_size,
            host=self._cfg.host,
            port=self._cfg.port,
            user=self._cfg.user,
            password=self._cfg.password,
            database=self._cfg.database,
            autocommit=False,
        )
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        logger.info(f"MySQL connected: {self._cfg.host}:{self._cfg.port}/{self._cfg.database}")

    @contextmanager
    def _get_conn(self):
        conn = self._pool.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    async def close(self):
        logger.info("MySQL connection pool released")

    # ═══════════════════════════════════════════════════════════
    # SOURCE DATA: COMPANY
    # ═══════════════════════════════════════════════════════════

    def get_company(self, company_id: str) -> dict | None:
        """Fetch from companies table, return in UI Entity shape."""
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM companies WHERE company_id = %s", (company_id,))
            row = cursor.fetchone()
        if not row:
            return None
        cid = str(row["company_id"])
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT COALESCE(SUM(total), 0) AS vol FROM bills WHERE company_id = %s",
                (cid,),
            )
            total_volume = float(cursor.fetchone()["vol"])
        return {
            "id": cid,
            "name": row.get("company_name"),
            "ein": _format_ein(row.get("ein")),
            "contactName": row.get("primary_contact"),
            "email": row.get("email"),
            "phone": _format_phone(row.get("phone")),
            "website": row.get("website"),
            "industry": row.get("industry_category"),
            "naics": row.get("industry_category"),
            "legalStructure": row.get("legal_structure"),
            "address": row.get("street_address"),
            "city": row.get("city"),
            "state": row.get("state"),
            "zip": row.get("zip"),
            "confidence": 1.0,
            "vendors": 0,
            "clients": 0,
            "volume": total_volume,
            "variants": [row["legal_name"]] if row.get("legal_name") else [],
            "commodities": [row["industry_category"]] if row.get("industry_category") else [],
        }

    # ═══════════════════════════════════════════════════════════
    # SOURCE DATA: MONTHLY VOLUME (bills table)
    # ═══════════════════════════════════════════════════════════

    def get_monthly_volume(self, entity_id: str, company_id: str = None) -> list[dict]:
        """Monthly volume trend from bills table."""
        months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)

            if entity_id.startswith("G-"):
                # Golden record → find vendor IDs via resolution_audit → query bills
                sql = """
                    SELECT YEAR(b.bill_date) AS yr, MONTH(b.bill_date) AS mo,
                           ROUND(SUM(b.total) / 1000) AS vol
                    FROM bills b
                    WHERE b.vendor_id IN (
                        SELECT DISTINCT CAST(SUBSTRING(ra.record_id, 3) AS UNSIGNED)
                        FROM resolution_audit ra
                        WHERE ra.target_golden_id = %s
                          AND ra.record_id LIKE 'v-%%'
                    )
                """
                params = [entity_id]
                if company_id:
                    sql += " AND b.company_id = %s"
                    params.append(company_id)
                sql += " GROUP BY YEAR(b.bill_date), MONTH(b.bill_date) ORDER BY yr, mo"
                cursor.execute(sql, params)
            else:
                # Company ID → all bills for that company
                cursor.execute("""
                    SELECT YEAR(bill_date) AS yr, MONTH(bill_date) AS mo,
                           ROUND(SUM(total) / 1000) AS vol
                    FROM bills
                    WHERE company_id = %s
                    GROUP BY YEAR(bill_date), MONTH(bill_date)
                    ORDER BY yr, mo
                """, (entity_id,))

            rows = cursor.fetchall()
            result = []
            for r in rows:
                mo = int(r["mo"])
                result.append({"month": months[mo], "vol": int(r["vol"] or 0)})
            return result[-12:]

    # ═══════════════════════════════════════════════════════════
    # PENDING RESOLUTION (OLTP work queue)
    # ═══════════════════════════════════════════════════════════

    def get_pending_matches(self, neo4j_client=None) -> list[dict]:
        """Pending matches enriched with entity data from Neo4j.

        Reads pending_resolution work queue from MySQL, then looks up
        orphan and candidate entities from Neo4j (primary golden record store).
        """
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT *
                FROM pending_resolution
                WHERE status = 'PENDING'
                ORDER BY created_at DESC
            """)
            pending_rows = cursor.fetchall()

        results = []
        for pr in pending_rows:
            orphan_entity = None
            candidate_entity = None
            oid = pr.get("orphan_golden_id")
            cid = pr.get("candidate_golden_id")

            if neo4j_client and neo4j_client.available:
                if oid:
                    orphan_entity = neo4j_client.get_entity(oid)
                if cid:
                    candidate_entity = neo4j_client.get_entity(cid)

            dim_scores = _parse_json(pr.get("dimension_scores")) or {}
            if "identity" in dim_scores:
                dim_scores["name"] = dim_scores.pop("identity")

            orphan_city = (orphan_entity or {}).get("city", "")
            orphan_state = (orphan_entity or {}).get("state", "")
            location = f"{orphan_city}, {orphan_state}".strip(", ")

            shared = []
            if neo4j_client and neo4j_client.available and oid and cid:
                shared = neo4j_client.get_common_neighbors(oid, cid).get("common_neighbors", [])
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

    def resolve_match(self, match_id: str, resolution: str) -> dict:
        """Accept or reject a pending match.

        accept → execute full merge (golden records + audit).
        reject → mark pending as REJECTED, mark orphan GR as REJECTED.

        Note: This still writes to golden_records + resolution_audit via MySQL.
        Transitional until pending resolution is fully decoupled.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        if resolution == "accept":
            self._execute_accepted_merge(match_id, now)
            return {"matchId": match_id, "resolution": resolution, "resolvedAt": now_iso}

        # Reject
        with self._get_conn() as conn:
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    "SELECT orphan_golden_id FROM pending_resolution WHERE match_id = %s",
                    (match_id,),
                )
                pr = cursor.fetchone()
                cursor.execute(
                    "UPDATE pending_resolution SET status = 'REJECTED', reviewer = 'user', reviewed_at = %s WHERE match_id = %s",
                    (now, match_id),
                )
                if pr and pr.get("orphan_golden_id"):
                    cursor.execute(
                        "UPDATE golden_records SET status = 'REJECTED' WHERE golden_record_id = %s",
                        (pr["orphan_golden_id"],),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {"matchId": match_id, "resolution": resolution, "resolvedAt": now_iso}

    def _execute_accepted_merge(self, match_id: str, now: datetime):
        """Single-transaction merge: update survivor GR, mark orphan MERGED, update pending, write audit.

        Transitional: still operates on MySQL golden_records + resolution_audit.
        """
        with self._get_conn() as conn:
            try:
                cursor = conn.cursor(dictionary=True)

                cursor.execute("SELECT * FROM pending_resolution WHERE match_id = %s", (match_id,))
                pr = cursor.fetchone()
                if not pr:
                    raise ValueError(f"Pending resolution {match_id} not found")

                orphan_id = pr["orphan_golden_id"]
                candidate_id = pr["candidate_golden_id"]

                cursor.execute("SELECT * FROM golden_records WHERE golden_record_id = %s", (orphan_id,))
                orphan_gr = cursor.fetchone()
                cursor.execute("SELECT * FROM golden_records WHERE golden_record_id = %s", (candidate_id,))
                candidate_gr = cursor.fetchone()
                if not orphan_gr or not candidate_gr:
                    raise ValueError(f"Golden record(s) not found: orphan={orphan_id}, candidate={candidate_id}")

                orphan_variants = _parse_json(orphan_gr.get("name_variants")) or []
                candidate_variants = _parse_json(candidate_gr.get("name_variants")) or []
                merged_variants = list(set(candidate_variants) | set(orphan_variants))

                orphan_sources = _parse_json(orphan_gr.get("source_records")) or []
                candidate_sources = _parse_json(candidate_gr.get("source_records")) or []
                merged_sources = list(set(candidate_sources) | set(orphan_sources))

                new_source_count = len(merged_sources)
                old_confidence = float(candidate_gr["confidence"]) if candidate_gr.get("confidence") is not None else 0.5
                new_confidence = min(0.99, old_confidence + 0.05)

                cursor.execute("""
                    UPDATE golden_records
                    SET name_variants = %s,
                        source_records = %s,
                        source_count = %s,
                        confidence = %s,
                        updated_at = %s
                    WHERE golden_record_id = %s
                """, (
                    json.dumps(merged_variants),
                    json.dumps(merged_sources),
                    new_source_count,
                    new_confidence,
                    now,
                    candidate_id,
                ))

                cursor.execute("""
                    UPDATE golden_records
                    SET status = 'MERGED', merged_into = %s, updated_at = %s
                    WHERE golden_record_id = %s
                """, (candidate_id, now, orphan_id))

                # Migrate orphan's relationships to survivor
                cursor.execute(
                    "SELECT source_entity_id, target_entity_id FROM relationships WHERE source_entity_id = %s OR target_entity_id = %s",
                    (candidate_id, candidate_id),
                )
                existing = {(r["source_entity_id"], r["target_entity_id"]) for r in cursor.fetchall()}

                cursor.execute(
                    "SELECT edge_id, source_entity_id, target_entity_id FROM relationships WHERE source_entity_id = %s OR target_entity_id = %s",
                    (orphan_id, orphan_id),
                )
                orphan_edges = cursor.fetchall()

                for edge in orphan_edges:
                    new_src = candidate_id if edge["source_entity_id"] == orphan_id else edge["source_entity_id"]
                    new_tgt = candidate_id if edge["target_entity_id"] == orphan_id else edge["target_entity_id"]
                    if new_src == new_tgt:
                        cursor.execute("DELETE FROM relationships WHERE edge_id = %s", (edge["edge_id"],))
                    elif (new_src, new_tgt) in existing:
                        cursor.execute("DELETE FROM relationships WHERE edge_id = %s", (edge["edge_id"],))
                    else:
                        cursor.execute(
                            "UPDATE relationships SET source_entity_id = %s, target_entity_id = %s, updated_at = %s WHERE edge_id = %s",
                            (new_src, new_tgt, now, edge["edge_id"]),
                        )
                        existing.add((new_src, new_tgt))

                cursor.execute("""
                    UPDATE pending_resolution
                    SET status = 'MERGED', reviewer = 'user', reviewed_at = %s
                    WHERE match_id = %s
                """, (now, match_id))

                audit_id = f"A-{uuid.uuid4().hex[:8]}"
                trigger_type = pr.get("trigger_type", "AI_AGENT")

                def _gr_snapshot(row):
                    if not row:
                        return None
                    out = {}
                    for k, v in row.items():
                        if hasattr(v, "isoformat"):
                            out[k] = v.isoformat()
                        elif isinstance(v, (int, float, str, bool, type(None))):
                            out[k] = v
                        else:
                            out[k] = str(v)
                    return out

                gr_before = _gr_snapshot(candidate_gr)
                cursor.execute("SELECT * FROM golden_records WHERE golden_record_id = %s", (candidate_id,))
                gr_after = _gr_snapshot(cursor.fetchone())

                cursor.execute("""
                    INSERT INTO resolution_audit (
                        audit_id, event_id, record_id, perspective, decision,
                        trigger_type, target_golden_id, absorbed_golden_id,
                        confidence, dimension_scores, reasoning, key_factors,
                        candidates_evaluated, llm_calls, embedding_calls,
                        total_duration_ms, evaluation_chain,
                        golden_record_before, golden_record_after, created_at
                    ) VALUES (
                        %s, %s, %s, 'GLOBAL', 'MERGE',
                        %s, %s, %s,
                        %s, %s, %s, %s,
                        0, 0, 0,
                        0, '[]',
                        %s, %s, %s
                    )
                """, (
                    audit_id,
                    f"user-accept-{match_id}",
                    orphan_id,
                    trigger_type,
                    candidate_id,
                    orphan_id,
                    float(pr["confidence"]) if pr.get("confidence") is not None else 0.0,
                    pr.get("dimension_scores", "{}"),
                    f"User accepted merge of {orphan_id} into {candidate_id}",
                    json.dumps(["user_accepted"]),
                    json.dumps(gr_before),
                    json.dumps(gr_after),
                    now,
                ))

                conn.commit()
                logger.info(f"Accepted merge: {orphan_id} → {candidate_id} (match={match_id})")

            except Exception:
                conn.rollback()
                logger.error(f"Accepted merge ROLLED BACK: match_id={match_id}")
                raise

    # ═══════════════════════════════════════════════════════════
    # CONNECTIONS
    # ═══════════════════════════════════════════════════════════

    def get_auto_connections(self, user_id: str = "1") -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM auto_connections
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_id,))
            rows = cursor.fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r["connection_id"],
                "type": r["conn_type"],
                "source": r.get("source_doc"),
                "sourceDate": r.get("source_date"),
                "entity": {"id": r.get("entity_id")},
                "resolution": r.get("resolution_type", "auto"),
                "tier": r.get("tier", 1),
                "confidence": float(r["confidence"]) if r.get("confidence") is not None else None,
                "latency": f"{r['latency_ms']}ms" if r.get("latency_ms") else None,
                "time": _time_ago(r.get("created_at")),
            })
        return results

    def get_manual_connections(self, user_id: str = "1") -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM manual_connections
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_id,))
            rows = cursor.fetchall()

        results = []
        for r in rows:
            entity = _parse_json(r.get("entity_snapshot"))
            results.append({
                "id": r["connection_id"],
                "type": r["conn_type"],
                "entity": entity or {"id": r.get("entity_id")},
                "addedVia": r.get("added_via"),
                "confidence": float(r["confidence"]) if r.get("confidence") is not None else None,
                "time": _time_ago(r.get("created_at")),
            })
        return results

    def add_connection(self, payload: dict, user_id: str = "1") -> dict:
        conn_id = f"mc-{uuid.uuid4().hex[:8]}"
        conn_type = payload.get("connType", "vendor")
        entity_data = payload.get("entity")
        entity_id = entity_data.get("id") if entity_data else None
        added_via = "Matched to existing entity" if entity_id else "Created as new entity"
        confidence = 0.91 if entity_id else None

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO manual_connections
                    (connection_id, user_id, conn_type, entity_id, entity_snapshot, added_via, confidence)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                conn_id, user_id, conn_type, entity_id,
                json.dumps(entity_data) if entity_data else None,
                added_via, confidence,
            ))
            conn.commit()

        return {
            "id": conn_id,
            "type": conn_type,
            "entity": entity_data or {"id": entity_id},
            "addedVia": added_via,
            "confidence": confidence,
            "time": "Just now",
        }

    # ═══════════════════════════════════════════════════════════
    # ALERTS
    # ═══════════════════════════════════════════════════════════

    def insert_alert(
        self,
        alert_id: str,
        connection_id: str,
        alert_type: str,
        title: str,
        message: str = None,
        entity_name: str = None,
        target_entity_id: str = None,
        confidence: float = None,
        user_id: str = "1",
    ):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO connection_alerts
                    (alert_id, connection_id, user_id, alert_type, title,
                     message, entity_name, target_entity_id, confidence)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                alert_id, connection_id, user_id, alert_type, title,
                message, entity_name, target_entity_id, confidence,
            ))
            conn.commit()

    def get_alerts(self, user_id: str = "1") -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM connection_alerts
                WHERE user_id = %s AND dismissed = FALSE
                ORDER BY created_at DESC
                LIMIT 20
            """, (user_id,))
            rows = cursor.fetchall()
        return [
            {
                "id": r["alert_id"],
                "connectionId": r["connection_id"],
                "type": r["alert_type"],
                "title": r["title"],
                "message": r.get("message"),
                "entityName": r.get("entity_name"),
                "targetEntityId": r.get("target_entity_id"),
                "confidence": float(r["confidence"]) if r.get("confidence") is not None else None,
                "time": _time_ago(r.get("created_at")),
            }
            for r in rows
        ]

    def dismiss_alert(self, alert_id: str):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE connection_alerts SET dismissed = TRUE WHERE alert_id = %s",
                (alert_id,),
            )
            conn.commit()

    def update_connection_agent_status(
        self,
        connection_id: str,
        status: str,
        decision: str = None,
        golden_record_id: str = None,
    ):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE manual_connections
                SET agent_status = %s,
                    agent_decision = %s,
                    agent_golden_record_id = %s,
                    agent_resolved_at = CURRENT_TIMESTAMP(3)
                WHERE connection_id = %s
            """, (status, decision, golden_record_id, connection_id))
            conn.commit()

    # ═══════════════════════════════════════════════════════════
    # NATIVE OVERRIDES
    # ═══════════════════════════════════════════════════════════

    def get_all_overrides(self, user_id: str = "1") -> dict:
        """Returns {entityId: {field: value, ...}, ...}."""
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT entity_id, overrides FROM native_overrides WHERE user_id = %s",
                (user_id,),
            )
            rows = cursor.fetchall()
        result = {}
        for r in rows:
            result[r["entity_id"]] = _parse_json(r["overrides"]) or {}
        return result

    def get_override(self, entity_id: str, user_id: str = "1") -> dict | None:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT overrides FROM native_overrides WHERE user_id = %s AND entity_id = %s",
                (user_id, entity_id),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return _parse_json(row["overrides"])

    def save_override(self, entity_id: str, fields: dict, user_id: str = "1") -> dict:
        """JSON_MERGE_PATCH upsert."""
        fields_json = json.dumps(fields)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO native_overrides (user_id, entity_id, overrides)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE overrides = JSON_MERGE_PATCH(overrides, VALUES(overrides))
            """, (user_id, entity_id, fields_json))
            conn.commit()
        return self.get_override(entity_id, user_id)

    def delete_override_field(self, entity_id: str, field: str, user_id: str = "1") -> dict | None:
        """Remove a single field from the overrides JSON."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE native_overrides
                SET overrides = JSON_REMOVE(overrides, %s)
                WHERE user_id = %s AND entity_id = %s
            """, (f"$.{field}", user_id, entity_id))
            conn.commit()

            cursor2 = conn.cursor(dictionary=True)
            cursor2.execute(
                "SELECT overrides FROM native_overrides WHERE user_id = %s AND entity_id = %s",
                (user_id, entity_id),
            )
            row = cursor2.fetchone()
            if row:
                overrides = _parse_json(row["overrides"])
                if not overrides or overrides == {}:
                    cursor.execute(
                        "DELETE FROM native_overrides WHERE user_id = %s AND entity_id = %s",
                        (user_id, entity_id),
                    )
                    conn.commit()
                    return None
                return overrides
        return None

    # ═══════════════════════════════════════════════════════════
    # NATIVE MERGES
    # ═══════════════════════════════════════════════════════════

    def get_merges(self, user_id: str = "1") -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM native_merges
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_id,))
            rows = cursor.fetchall()
        return [self._merge_to_dict(r) for r in rows]

    def create_merge(self, payload: dict, user_id: str = "1") -> dict:
        merge_id = f"nm-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        migrated = json.dumps(payload.get("migratedRelationships", []))

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO native_merges
                    (merge_id, user_id, source_entity_id, target_entity_id,
                     origin, reason, migrated_relationships)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                merge_id, user_id,
                payload["sourceEntityId"], payload["targetEntityId"],
                "user", payload.get("reason", ""),
                migrated,
            ))
            conn.commit()

        return {
            "id": merge_id,
            "sourceEntityId": payload["sourceEntityId"],
            "targetEntityId": payload["targetEntityId"],
            "origin": "user",
            "reason": payload.get("reason", ""),
            "migratedRelationships": payload.get("migratedRelationships", []),
            "timestamp": now,
        }

    def delete_merge(self, merge_id: str, user_id: str = "1") -> dict | None:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM native_merges WHERE merge_id = %s AND user_id = %s",
                (merge_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            result = self._merge_to_dict(row)
            cursor.execute(
                "DELETE FROM native_merges WHERE merge_id = %s AND user_id = %s",
                (merge_id, user_id),
            )
            conn.commit()
        return result

    def _merge_to_dict(self, row: dict) -> dict:
        created = row.get("created_at")
        if created and not isinstance(created, str):
            created = created.isoformat() if hasattr(created, 'isoformat') else str(created)
        return {
            "id": row["merge_id"],
            "sourceEntityId": row["source_entity_id"],
            "targetEntityId": row["target_entity_id"],
            "origin": row.get("origin", "user"),
            "reason": row.get("reason"),
            "migratedRelationships": _parse_json(row.get("migrated_relationships")) or [],
            "timestamp": created,
        }
