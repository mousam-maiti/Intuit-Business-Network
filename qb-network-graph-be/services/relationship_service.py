"""Relationship service — network, supply chain, shortest path."""
from __future__ import annotations

from repositories.base import AbstractRelationshipRepository, AbstractVolumeRepository


class RelationshipService:
    def __init__(
        self,
        relationship_repo: AbstractRelationshipRepository,
        volume_repo: AbstractVolumeRepository,
    ):
        self._repo = relationship_repo
        self._volume_repo = volume_repo

    def get_all(self, company_id: str = None) -> dict:
        return {"data": self._repo.get_all(company_id=company_id)}

    def get_for_entity(self, entity_id: str) -> dict:
        return {"data": self._repo.get_for_entity(entity_id)}

    def get_network(self, entity_id: str, depth: int = 2) -> dict:
        return {"data": self._repo.get_network(entity_id, depth=depth)}

    def get_supply_chain(self, entity_id: str, direction: str = "upstream",
                         depth: int = 5) -> dict:
        return {"data": self._repo.get_supply_chain(entity_id, direction=direction, max_depth=depth)}

    def get_shortest_path(self, id_a: str, id_b: str) -> dict:
        return {"data": self._repo.get_shortest_path(id_a, id_b)}

    def get_common_neighbors(self, id_a: str, id_b: str, limit: int = 20) -> dict:
        return {"data": self._repo.get_common_neighbors(id_a, id_b, limit=limit)}

    def get_cluster(self, entity_id: str, max_size: int = 20) -> dict:
        return {"data": self._repo.get_cluster(entity_id, max_size=max_size)}

    def get_impact(self, entity_id: str, max_depth: int = 3) -> dict:
        return {"data": self._repo.get_impact(entity_id, max_depth=max_depth)}

    def get_volume(self, entity_id: str, company_id: str = None) -> dict:
        return {"data": self._volume_repo.get_monthly_volume(entity_id, company_id=company_id)}
