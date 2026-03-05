"""Abstract interface for text embedding."""
from abc import ABC, abstractmethod


class AbstractEmbeddingProvider(ABC):
    """Text embedding for semantic similarity computation."""

    @abstractmethod
    def compute_similarity(self, orphan_texts: dict, candidate_texts: dict, weights: dict) -> dict: ...

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text string."""
        ...

    @property
    @abstractmethod
    def is_mock(self) -> bool: ...
