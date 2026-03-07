"""Abstract interface for text + vector search."""
from abc import ABC, abstractmethod


class AbstractSearchRepository(ABC):
    """Full-text + graph-based + vector entity search."""

    @abstractmethod
    def search_by_name(
        self, query: str, state_filter: str = None, city_filter: str = None,
        naics_filter: str = None, min_confidence: float = None, limit: int = 10,
    ) -> list[dict]: ...

    @abstractmethod
    def vector_search(
        self, query_vector: list[float], state_filter: str = None,
        naics_filter: str = None, top_k: int = 30,
    ) -> list[dict]:
        """Search entities by vector similarity using Neo4j vector index."""
        ...

    @abstractmethod
    def aggregate(
        self, group_by: str, state_filter: str = None,
        naics_filter: str = None, min_confidence: float = None,
    ) -> list[dict]: ...
