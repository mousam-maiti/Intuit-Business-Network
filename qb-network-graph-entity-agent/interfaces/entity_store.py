from __future__ import annotations

"""Abstract interface for golden record entity operations."""
from abc import ABC, abstractmethod


class AbstractEntityStore(ABC):
    """Golden record CRUD — merge, create, submit for review."""

    @abstractmethod
    async def merge(
        self,
        orphan_record_id: str,
        orphan_persona: dict,
        golden_record_id: str,
        merge_reasoning: dict,
        company_id: str,
        record_type: str = "vendor",
    ) -> dict:
        """Merge orphan into an existing golden record."""
        ...

    @abstractmethod
    async def create(
        self,
        orphan_record_id: str,
        orphan_persona: dict,
        creation_reasoning: dict,
        company_id: str,
        record_type: str = "vendor",
    ) -> dict:
        """Create a new golden record from orphan."""
        ...

    @abstractmethod
    async def submit_for_review(
        self,
        orphan_record_id: str,
        orphan_persona: dict,
        candidate_golden_record_id: str,
        review_reasoning: dict,
        company_id: str,
        record_type: str = "vendor",
    ) -> dict:
        """Submit ambiguous match for human review."""
        ...

    @abstractmethod
    async def merge_golden_records(
        self,
        survivor_id: str,
        absorbed_id: str,
        merge_reasoning: dict,
    ) -> dict:
        """Merge two golden records (used during re-evaluation)."""
        ...

    @abstractmethod
    async def describe(self, entity_id: str) -> dict:
        """Get entity profile for re-evaluation persona building."""
        ...
