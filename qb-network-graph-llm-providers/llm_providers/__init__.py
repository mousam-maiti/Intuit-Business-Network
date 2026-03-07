"""Shared LLM provider abstraction for QB Network Graph agents."""
from .base import LLMProvider


def create_llm_provider(provider: str = "gemini", **kwargs) -> LLMProvider:
    """Factory: create an LLMProvider by name."""
    if provider == "gemini":
        from .gemini_provider import GeminiLLMProvider
        return GeminiLLMProvider(**kwargs)
    raise ValueError(f"Unknown LLM provider: {provider}")


def create_embedding_provider(provider: str = "gemini", **kwargs):
    """Factory: create an EmbeddingProvider by name."""
    if provider == "gemini":
        from .gemini_provider import GeminiEmbeddingProvider
        return GeminiEmbeddingProvider(**kwargs)
    raise ValueError(f"Unknown embedding provider: {provider}")
