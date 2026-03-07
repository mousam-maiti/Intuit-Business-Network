"""MySQL-backed connection repository — auto/manual connections."""
from __future__ import annotations

import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from repositories.base import AbstractConnectionRepository

logger = logging.getLogger(__name__)


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


class MySQLConnectionRepository(AbstractConnectionRepository):
    """Auto and manual connections backed by MySQL."""

    def __init__(self, pool):
        self._pool = pool

    @contextmanager
    def _get_conn(self):
        conn = self._pool.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    def get_auto(self, user_id: str = "1") -> list[dict]:
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

    def get_manual(self, user_id: str = "1") -> list[dict]:
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

    def add(self, payload: dict, user_id: str = "1") -> dict:
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

    def update_agent_status(self, connection_id: str, status: str,
                            decision: str = None, golden_record_id: str = None):
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
