from __future__ import annotations

"""Abstract interface for candidate finding."""
from abc import ABC, abstractmethod


class AbstractCandidateFinder(ABC):
    """Finds candidate golden records matching an orphan persona."""

    @abstractmethod
    async def find(self, orphan_persona: dict, max_candidates: int = 20) -> dict:
        """Find candidate golden records by bucket key matching.

        Args:
            orphan_persona: Classified persona dict.
            max_candidates: Maximum candidates to return.

        Returns:
            dict with keys: candidates (list[dict]), bucket_stats (dict).
        """
        ...
