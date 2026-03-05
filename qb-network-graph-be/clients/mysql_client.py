"""
MySQL client for the REST API backend.

After the streaming lakehouse migration, MySQL retains:
  - Source data: companies, bills, invoices, payments
  - Connections: auto_connections, manual_connections
  - Native overrides & merges: user customizations

Entity reads (golden_records), graph queries (relationships), audit trail,
and search live in Neo4j (serving layer). Pending resolution, alerts, and
lineage data live in Paimon gold (source of truth).
"""
from __future__ import annotations
import json
import logging
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
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
