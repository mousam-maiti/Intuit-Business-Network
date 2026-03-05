"""Abstract interface for relationship CRUD + graph traversal."""
from abc import ABC, abstractmethod
from typing import Optional


class AbstractRelationshipRepository(ABC):
    """Edge CRUD + directed traversal on the graph store."""

    @abstractmethod
    def create(self, source_id: str, target_id: str, rel_type: str, properties: dict) -> None: ...

    @abstractmethod
    def merge_entities(self, survivor_id: str, absorbed_id: str) -> None: ...

    @abstractmethod
    def get_neighbors(self, entity_id: str, direction: str = "both", rel_type: str = None) -> list[dict]: ...

    @abstractmethod
    def get_relationships(self, company_id: str, connection_type: str = "all", sort_by: str = "volume", limit: int = 20) -> list[dict]: ...

    @abstractmethod
    def traverse_supply_chain(self, start_id: str, hops: list[str], max_per_hop: int = 5, min_volume: float = 0) -> list[dict]: ...

    @abstractmethod
    def find_shortest_path(self, start_id: str, end_id: str) -> Optional[dict]: ...

    @abstractmethod
    def find_common_neighbors(self, entity_a: str, entity_b: str, limit: int = 20) -> list[dict]: ...

    @abstractmethod
    def find_cluster(self, entity_id: str, max_size: int = 20) -> Optional[dict]: ...

    @abstractmethod
    def assess_impact(self, entity_id: str, max_depth: int = 3) -> Optional[dict]: ...
