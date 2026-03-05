"""Paimon-backed alert repository — connection lifecycle alerts from Paimon gold via pypaimon."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from repositories.base import AbstractAlertRepository

logger = logging.getLogger(__name__)


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


class PaimonAlertRepository(AbstractAlertRepository):
    """Connection lifecycle alerts backed by Paimon gold.connection_alerts via pypaimon reads + Flink writes."""

    def __init__(self, paimon_client, flink_client=None):
        self._paimon = paimon_client
        self._flink = flink_client

    def insert(self, alert_id: str, connection_id: str, alert_type: str,
               title: str, message: str = None, entity_name: str = None,
               target_entity_id: str = None, confidence: float = None,
               user_id: str = "1"):
        if not self._flink or not self._flink.available:
            logger.warning("Flink SQL Gateway unavailable — cannot write alert")
            return
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self._flink.execute_update(
            "INSERT INTO gold.connection_alerts "
            "(alert_id, connection_id, user_id, alert_type, title, message, "
            "entity_name, target_entity_id, confidence, dismissed, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, TIMESTAMP %s)",
            [
                alert_id, connection_id, user_id, alert_type, title,
                message, entity_name, target_entity_id, confidence, now_ts,
            ],
        )

    def get_all(self, user_id: str = "1") -> list[dict]:
        all_rows = self._paimon.read_table("gold.connection_alerts")
        # Filter: matching user_id and not dismissed
        rows = [
            r for r in all_rows
            if str(r.get("user_id", "")) == str(user_id) and not r.get("dismissed")
        ]
        # Sort by created_at DESC
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        results = []
        for r in rows[:20]:
            results.append({
                "id": r.get("alert_id"),
                "connectionId": r.get("connection_id"),
                "type": r.get("alert_type"),
                "title": r.get("title"),
                "message": r.get("message"),
                "entityName": r.get("entity_name"),
                "targetEntityId": r.get("target_entity_id"),
                "confidence": float(r["confidence"]) if r.get("confidence") is not None else None,
                "time": _time_ago(r.get("created_at")),
            })
        return results

    def dismiss(self, alert_id: str):
        if not self._flink or not self._flink.available:
            logger.warning("Flink SQL Gateway unavailable — cannot dismiss alert")
            return
        self._flink.execute_update(
            "INSERT INTO gold.connection_alerts (alert_id, dismissed) VALUES (%s, TRUE)",
            [alert_id],
        )
