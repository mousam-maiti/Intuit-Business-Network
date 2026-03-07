"""
Embedding client — semantic similarity via pluggable EmbeddingProvider.

Uses the shared llm_providers package for embedding generation.
Falls back to deterministic mock vectors if API unavailable.
"""
from __future__ import annotations
import hashlib
import logging
import time
import numpy as np
from typing import Optional
from config import EmbeddingConfig

logger = logging.getLogger(__name__)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None:
        return 0.0
    dot = np.dot(a, b)
    norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


class EmbeddingClient:
    def __init__(self, cfg: EmbeddingConfig):
        self._cfg = cfg
        self._provider = None
        self._available = False
        self._using_mock = False
        self._model_name = cfg.model
        self._dimension = cfg.dimension

    async def connect(self):
        from llm_providers import create_embedding_provider
        try:
            self._provider = create_embedding_provider(
                provider=self._cfg.provider,
                model=self._cfg.model,
                dim=self._cfg.dimension,
                task_type=self._cfg.task_type,
            )
            await self._provider.connect()
            if self._provider.available:
                self._available = True
                self._dimension = self._provider.dimension
                logger.info(f"Embedding connected: {self._model_name} ({self._dimension}d)")
            else:
                logger.warning("Embedding provider unavailable — using mock embeddings")
                self._using_mock = True
        except Exception as e:
            logger.warning(f"Embedding init failed ({e}) — using mock embeddings")
            self._using_mock = True

    def embed(self, text: str) -> Optional[np.ndarray]:
        """Embed a single text string. Returns numpy array."""
        if not text or not text.strip():
            return None

        if self._using_mock:
            h = hashlib.md5(text.encode()).hexdigest()
            seed = int(h[:8], 16)
            rng = np.random.RandomState(seed)
            vec = rng.randn(self._dimension).astype(np.float32)
            return vec / np.linalg.norm(vec)

        return self._provider.embed(text)

    def embed_batch(self, texts: list[str]) -> list[Optional[np.ndarray]]:
        """Embed multiple texts. Returns list of numpy arrays (or None for empty)."""
        if self._using_mock:
            return [self.embed(t) for t in texts]
        return self._provider.embed_batch(texts)

    def compute_similarity(
        self,
        orphan_texts: dict[str, str],
        candidate_texts: dict[str, str],
        weights: dict[str, float],
    ) -> dict:
        """Compute per-dimension semantic similarity.

        Input dicts have keys: name, industry, commodities, location
        Returns: per-dimension scores + weighted composite + metadata
        """
        start = time.time()
        dimensions = ["name", "industry", "commodities", "location"]
        scores: dict[str, float] = {}
        valid_weight_sum = 0.0
        weighted_sum = 0.0

        dim_to_weight_key = {
            "name": "identity",
            "industry": "industry",
            "commodities": "commodity",
            "location": "location",
        }

        for dim in dimensions:
            o_text = orphan_texts.get(dim, "")
            c_text = candidate_texts.get(dim, "")
            if not o_text or not c_text:
                scores[f"{dim}_similarity"] = 0.0
                continue

            o_vec = self.embed(o_text)
            c_vec = self.embed(c_text)
            sim = _cosine(o_vec, c_vec)
            # Clamp to [0, 1]
            sim = max(0.0, min(1.0, sim))
            scores[f"{dim}_similarity"] = round(sim, 4)

            wk = dim_to_weight_key.get(dim, dim)
            w = weights.get(wk, 0.25)
            valid_weight_sum += w
            weighted_sum += sim * w

        composite = round(weighted_sum / valid_weight_sum, 4) if valid_weight_sum > 0 else 0.0
        elapsed_ms = int((time.time() - start) * 1000)

        return {
            "name_similarity": scores.get("name_similarity", 0.0),
            "industry_similarity": scores.get("industry_similarity", 0.0),
            "commodity_similarity": scores.get("commodities_similarity", 0.0),
            "location_similarity": scores.get("location_similarity", 0.0),
            "composite_similarity": composite,
            "model_used": "mock" if self._using_mock else self._model_name,
            "inference_ms": elapsed_ms,
        }

    def embed_text(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text string (returns list[float])."""
        vec = self.embed(text)
        if vec is None:
            return []
        return vec.tolist()

    @property
    def is_mock(self) -> bool:
        return self._using_mock
