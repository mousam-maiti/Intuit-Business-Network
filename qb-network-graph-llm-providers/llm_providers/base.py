"""Abstract interfaces for LLM and Embedding providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import numpy as np


class LLMProvider(ABC):
    """Text generation provider."""

    @abstractmethod
    async def connect(self):
        """Initialize the provider (API key, model setup, etc.)."""
        ...

    @abstractmethod
    def generate(self, prompt: str, system: str = None,
                 temperature: float = None, max_tokens: int = None,
                 response_format: str = None) -> str:
        """One-shot generation. Returns text."""
        ...

    @abstractmethod
    def chat(self, history: list[dict], message: str,
             system: str = None, temperature: float = None,
             max_tokens: int = None) -> str:
        """Multi-turn chat. Returns text response.

        History format: [{"role": "user"|"assistant", "parts": [str]}, ...]
        The provider maps roles internally (e.g. "assistant" -> "model" for Gemini).
        """
        ...

    @property
    @abstractmethod
    def available(self) -> bool:
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...


class EmbeddingProvider(ABC):
    """Text embedding provider."""

    @abstractmethod
    async def connect(self):
        """Initialize the provider and verify connectivity."""
        ...

    @abstractmethod
    def embed(self, text: str) -> Optional[np.ndarray]:
        """Embed a single text. Returns numpy vector or None."""
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[Optional[np.ndarray]]:
        """Embed multiple texts. Returns list of numpy arrays (or None for empty)."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...

    @property
    @abstractmethod
    def available(self) -> bool:
        ...
