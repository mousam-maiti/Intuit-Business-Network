"""Native service — overrides and merges."""
from __future__ import annotations

from exceptions import EntityNotFoundError
from repositories.base import AbstractNativeRepository


class NativeService:
    def __init__(self, native_repo: AbstractNativeRepository):
        self._repo = native_repo

    # ── Overrides ────────────────────────────────────────────

    def get_all_overrides(self) -> dict:
        return {"data": self._repo.get_all_overrides()}

    def get_override(self, entity_id: str) -> dict:
        return {"data": self._repo.get_override(entity_id)}

    def save_override(self, entity_id: str, fields: dict) -> dict:
        return {"data": self._repo.save_override(entity_id, fields)}

    def delete_override_field(self, entity_id: str, field: str) -> dict:
        return {"data": self._repo.delete_override_field(entity_id, field)}

    # ── Merges ───────────────────────────────────────────────

    def get_merges(self) -> dict:
        return {"data": self._repo.get_merges()}

    def create_merge(self, payload: dict) -> dict:
        return {"data": self._repo.create_merge(payload)}

    def delete_merge(self, merge_id: str) -> dict:
        result = self._repo.delete_merge(merge_id)
        if result is None:
            raise EntityNotFoundError(merge_id)
        return {"data": result}
