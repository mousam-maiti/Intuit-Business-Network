"""Abstract interface for audit trail operations."""
from abc import ABC, abstractmethod


class AbstractAuditRepository(ABC):
    """Audit entry CRUD — write decisions, read trails."""

    @abstractmethod
    def write(self, audit_dict: dict) -> str: ...

    @abstractmethod
    def get_trail(self, entity_id: str, limit: int = 50) -> list[dict]: ...
