"""MySQL-backed native repository — overrides and merges."""
from __future__ import annotations

import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from repositories.base import AbstractNativeRepository

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


class MySQLNativeRepository(AbstractNativeRepository):
    """Native overrides and merges backed by MySQL."""

    def __init__(self, pool):
        self._pool = pool

    @contextmanager
    def _get_conn(self):
        conn = self._pool.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    # ── Overrides ────────────────────────────────────────────

    def get_all_overrides(self, user_id: str = "1") -> dict:
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

    def get_override(self, entity_id: str, user_id: str = "1") -> Optional[dict]:
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

    def delete_override_field(self, entity_id: str, field: str, user_id: str = "1") -> Optional[dict]:
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

    # ── Merges ───────────────────────────────────────────────

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

    def delete_merge(self, merge_id: str, user_id: str = "1") -> Optional[dict]:
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

    @staticmethod
    def _merge_to_dict(row: dict) -> dict:
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
