from __future__ import annotations

"""Abstract interface for semantic similarity computation."""
from abc import ABC, abstractmethod


class AbstractSimilarityProvider(ABC):
    """Computes embedding-based semantic similarity between records."""

    @abstractmethod
    async def compute(self, orphan_persona: dict, candidate: dict) -> dict:
        """Compute semantic similarity between orphan and candidate.

        Args:
            orphan_persona: Classified persona dict.
            candidate: Candidate golden record dict.

        Returns:
            SimilarityResult-compatible dict with per-dimension similarities.
        """
        ...
