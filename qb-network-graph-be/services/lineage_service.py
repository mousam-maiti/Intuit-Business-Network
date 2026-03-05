"""Lineage service — audit trail, snapshots, time-travel restore."""
from __future__ import annotations

from repositories.base import AbstractLineageRepository, AbstractEntityRepository


class LineageService:
    def __init__(self, lineage_repo: AbstractLineageRepository, entity_repo: AbstractEntityRepository = None):
        self._repo = lineage_repo
        self._entity_repo = entity_repo

    def get_entities(self) -> dict:
        entities = self._repo.get_entities_with_audit()
        if not entities and self._entity_repo and self._entity_repo.available:
            # Fallback: return all Neo4j entities when no audit data exists yet
            all_entities = self._entity_repo.get_all()
            entities = [{"id": e["id"], "name": e["name"], "industry": e.get("industry"), "status": "ACTIVE"} for e in all_entities]
        return {"data": entities}

    def get_trail(self, entity_id: str, limit: int = 100) -> dict:
        return {"data": self._repo.get_audit_trail(entity_id, limit)}

    def get_snapshot(self, entity_id: str, date: str) -> dict:
        return {"data": self._repo.get_snapshot(entity_id, date)}

    def restore(self, entity_id: str, snapshot: dict, audit_id: str) -> dict:
        return {"data": self._repo.restore(entity_id, snapshot, audit_id)}
