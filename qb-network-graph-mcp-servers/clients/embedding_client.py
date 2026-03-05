"""
Embedding client — Gemini embedding for semantic similarity + vector search.

Uses google-genai SDK (v1) with gemini-embedding-001 and output_dimensionality
to control vector size. Falls back to deterministic mock vectors if API unavailable.
"""
from __future__ import annotations
import logging
import time
import numpy as np
from typing import Optional
from config import EmbeddingConfig

logger = logging.getLogger(__name__)

# Try new google-genai SDK first, fall back to deprecated google.generativeai
_genai_client = None
HAS_GENAI = False
try:
    from google import genai as genai_new
    from google.genai import types as genai_types
    HAS_GENAI = True
except ImportError:
    pass


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
        self._available = False
        self._using_mock = False
        self._model_name = cfg.model
        self._dimension = cfg.dimension

    async def connect(self):
        global _genai_client

        if not HAS_GENAI:
            logger.warning("google-genai not installed — using mock embeddings")
            self._using_mock = True
            return

        import os
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set — using mock embeddings")
            self._using_mock = True
            return

        try:
            _genai_client = genai_new.Client(api_key=api_key)
            # Quick test with output_dimensionality
            result = _genai_client.models.embed_content(
                model=self._model_name,
                contents="test",
                config=genai_types.EmbedContentConfig(
                    output_dimensionality=self._dimension,
                ),
            )
            if result and result.embeddings:
                actual_dim = len(result.embeddings[0].values)
                self._available = True
                self._dimension = actual_dim
                logger.info(f"Gemini embedding connected: {self._model_name} ({self._dimension}d)")
            else:
                self._using_mock = True
                logger.warning("Gemini embedding test failed — using mock")
        except Exception as e:
            logger.warning(f"Gemini embedding unavailable ({e}) — using mock")
            self._using_mock = True

    def embed(self, text: str) -> Optional[np.ndarray]:
        """Embed a single text string. Returns numpy array."""
        if not text or not text.strip():
            return None

        if self._using_mock:
            # Deterministic mock: hash-based pseudo-random vector
            import hashlib
            h = hashlib.md5(text.encode()).hexdigest()
            seed = int(h[:8], 16)
            rng = np.random.RandomState(seed)
            vec = rng.randn(self._dimension).astype(np.float32)
            return vec / np.linalg.norm(vec)

        try:
            result = _genai_client.models.embed_content(
                model=self._model_name,
                contents=text,
                config=genai_types.EmbedContentConfig(
                    output_dimensionality=self._dimension,
                ),
            )
            return np.array(result.embeddings[0].values, dtype=np.float32)
        except Exception as e:
            logger.error(f"Embedding failed for text '{text[:50]}': {e}")
            return None

    def embed_batch(self, texts: list[str]) -> list[Optional[np.ndarray]]:
        """Embed multiple texts. Returns list of numpy arrays (or None for empty)."""
        return [self.embed(t) for t in texts]

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
