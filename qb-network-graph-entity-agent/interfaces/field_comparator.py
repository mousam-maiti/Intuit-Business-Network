from __future__ import annotations

"""Abstract interface for deterministic field comparison."""
from abc import ABC, abstractmethod


class AbstractFieldComparator(ABC):
    """Deterministic per-dimension field comparison."""

    @abstractmethod
    async def compare(self, orphan_persona: dict, candidate: dict) -> dict:
        """Compare orphan persona against a candidate golden record.

        Args:
            orphan_persona: Classified persona dict.
            candidate: Candidate golden record dict.

        Returns:
            ComparisonResult-compatible dict with per-dimension scores and composite.
        """
        ...
