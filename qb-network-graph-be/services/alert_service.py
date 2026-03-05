"""Alert service — connection lifecycle alerts."""
from __future__ import annotations

from repositories.base import AbstractAlertRepository


class AlertService:
    def __init__(self, alert_repo: AbstractAlertRepository):
        self._repo = alert_repo

    def get_all(self) -> dict:
        return {"data": self._repo.get_all()}

    def dismiss(self, alert_id: str) -> dict:
        self._repo.dismiss(alert_id)
        return {"data": {"dismissed": True}}
