"""Abstract interface for golden record entity CRUD."""
from abc import ABC, abstractmethod
from typing import Optional


class AbstractEntityRepository(ABC):
    """Entity CRUD + bucket key lookups + vector search on the primary store."""

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def upsert(self, entity: dict) -> None: ...

    @abstractmethod
    def get(self, entity_id: str) -> Optional[dict]: ...

    @abstractmethod
    def get_all(self, active_only: bool = True) -> list[dict]: ...

    @abstractmethod
    def delete(self, entity_id: str) -> None: ...

    @abstractmethod
    def find_by_bucket_key(self, bucket_key: str) -> list[str]: ...

    @abstractmethod
    def vector_search(
        self, query_vector: list[float], state_filter: str = None,
        naics_filter: str = None, top_k: int = 30, min_score: float = 0.3,
    ) -> list[dict]:
        """Search entities by vector similarity. Filters out results below min_score."""
        ...

    @abstractmethod
    def generate_id(self, prefix: str = "G") -> str: ...
