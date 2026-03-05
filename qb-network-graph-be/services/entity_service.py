"""Entity service — business logic for entity CRUD with fallback."""
from __future__ import annotations

from typing import Optional

from exceptions import EntityNotFoundError
from repositories.base import AbstractEntityRepository


class EntityService:
    def __init__(
        self,
        entity_repo: AbstractEntityRepository,
        fallback_repo=None,
    ):
        self._repo = entity_repo
        self._fallback = fallback_repo

    def list_entities(self, q: str = None, industry: str = None,
                      company_id: str = None) -> dict:
        results = self._repo.get_all(q=q, industry=industry, company_id=company_id)
        return {"data": results, "total": len(results)}

    def get_entity(self, entity_id: str) -> dict:
        entity = self._repo.get_by_id(entity_id)
        if not entity and self._fallback:
            entity = self._fallback.get_company(entity_id)
        if not entity:
            raise EntityNotFoundError(entity_id)
        return {"data": entity}

    def patch_entity(self, entity_id: str, fields: dict) -> dict:
        entity = self._repo.update(entity_id, fields)
        if not entity:
            raise EntityNotFoundError(entity_id)
        return {"data": entity}
