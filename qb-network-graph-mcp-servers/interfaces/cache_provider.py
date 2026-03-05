"""Abstract interface for caching."""
from abc import ABC, abstractmethod
from typing import Optional


class AbstractCacheProvider(ABC):
    """Cache-aside for hot subgraphs and traversal results."""

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    async def get_cached(self, key: str) -> Optional[dict]: ...

    @abstractmethod
    async def set_cached(self, key: str, value: dict, ttl: int = None) -> None: ...

    @abstractmethod
    async def invalidate_entity(self, entity_id: str) -> None: ...
