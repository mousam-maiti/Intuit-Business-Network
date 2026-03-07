"""Gemini implementations of LLMProvider and EmbeddingProvider."""
from __future__ import annotations

import logging
from typing import Optional

from .base import LLMProvider, EmbeddingProvider

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# New google-genai SDK (v1) — preferred for embeddings (supports output_dimensionality)
try:
    from google import genai as genai_new
    from google.genai import types as genai_types
    HAS_GENAI_NEW = True
except ImportError:
    HAS_GENAI_NEW = False


# ── Helpers ──────────────────────────────────────────────────

def _safe_text(response) -> str:
    """Safely extract text from a Gemini response.

    Handles MALFORMED_FUNCTION_CALL and empty responses.
    """
    try:
        candidate = response.candidates[0]
        finish = getattr(candidate, "finish_reason", None)
        if finish and (str(finish) == "MALFORMED_FUNCTION_CALL"
                       or getattr(finish, 'value', None) == 6
                       or str(finish) == "6"
                       or "MALFORMED" in str(finish).upper()):
            parts = candidate.content.parts if hasattr(candidate, "content") and candidate.content else []
            for part in parts:
                fc = getattr(part, "function_call", None)
                if fc:
                    import json
                    name = getattr(fc, "name", "unknown")
                    args = dict(fc.args) if hasattr(fc, "args") and fc.args else {}
                    return f"Thought: I need to look up this information.\nAction: {name}({json.dumps(args)})"
                if hasattr(part, "text") and part.text:
                    return part.text
            return ""
    except (IndexError, AttributeError):
        pass

    try:
        return response.text or ""
    except (ValueError, AttributeError):
        try:
            parts = response.candidates[0].content.parts
            return parts[0].text if parts else ""
        except (IndexError, AttributeError):
            return ""


# ── LLM Provider ─────────────────────────────────────────────

class GeminiLLMProvider(LLMProvider):
    """Google Gemini text generation provider."""

    def __init__(self, api_key: str = None, model: str = "gemini-2.5-pro",
                 temperature: float = 0.3, max_tokens: int = 4096):
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._available = False

    async def connect(self):
        if not HAS_GEMINI:
            logger.warning("google-generativeai package not installed")
            return
        import os
        api_key = self._api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set")
            return
        try:
            genai.configure(api_key=api_key)
            self._available = True
            logger.info(f"Gemini LLM connected: {self._model}")
        except Exception as e:
            logger.warning(f"Gemini LLM init failed: {e}")

    def generate(self, prompt: str, system: str = None,
                 temperature: float = None, max_tokens: int = None,
                 response_format: str = None) -> str:
        gen_config_kwargs = {
            "temperature": temperature if temperature is not None else self._temperature,
            "max_output_tokens": max_tokens or self._max_tokens,
        }
        if response_format == "json":
            gen_config_kwargs["response_mime_type"] = "application/json"

        model = genai.GenerativeModel(
            model_name=self._model,
            system_instruction=system,
            generation_config=genai.GenerationConfig(**gen_config_kwargs),
        )
        response = model.generate_content(prompt)
        return _safe_text(response)

    def chat(self, history: list[dict], message: str,
             system: str = None, temperature: float = None,
             max_tokens: int = None) -> str:
        gen_config_kwargs = {
            "temperature": temperature if temperature is not None else self._temperature,
            "max_output_tokens": max_tokens or self._max_tokens,
        }
        model = genai.GenerativeModel(
            model_name=self._model,
            system_instruction=system,
            generation_config=genai.GenerationConfig(**gen_config_kwargs),
        )

        # Map history roles: "assistant" -> "model" for Gemini
        gemini_history = []
        for msg in history:
            role = msg["role"]
            if role == "assistant":
                role = "model"
            gemini_history.append({"role": role, "parts": msg["parts"]})

        chat = model.start_chat(history=gemini_history)
        response = chat.send_message(message)
        return _safe_text(response)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def model_name(self) -> str:
        return self._model


# ── Embedding Provider ───────────────────────────────────────

class GeminiEmbeddingProvider(EmbeddingProvider):
    """Google Gemini text embedding provider.

    Tries the new google-genai SDK (v1, supports output_dimensionality) first,
    then falls back to the deprecated google.generativeai SDK.
    """

    def __init__(self, api_key: str = None, model: str = "text-embedding-004",
                 dim: int = 768, task_type: str = "SEMANTIC_SIMILARITY"):
        self._api_key = api_key
        self._model = model
        self._dimension = dim
        self._task_type = task_type
        self._available = False
        self._use_new_sdk = False
        self._genai_client = None  # google-genai Client instance

    async def connect(self):
        import os
        api_key = self._api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set")
            return

        # Try new google-genai SDK first (supports output_dimensionality)
        if HAS_GENAI_NEW:
            try:
                self._genai_client = genai_new.Client(api_key=api_key)
                result = self._genai_client.models.embed_content(
                    model=self._model,
                    contents="test",
                    config=genai_types.EmbedContentConfig(
                        output_dimensionality=self._dimension,
                    ),
                )
                if result and result.embeddings:
                    self._dimension = len(result.embeddings[0].values)
                    self._available = True
                    self._use_new_sdk = True
                    logger.info(f"Gemini embedding connected (genai v1): {self._model} ({self._dimension}d)")
                    return
            except Exception as e:
                logger.warning(f"google-genai SDK failed ({e}), trying legacy SDK")

        # Fallback to deprecated google.generativeai
        if HAS_GEMINI:
            try:
                genai.configure(api_key=api_key)
                result = genai.embed_content(
                    model=f"models/{self._model}",
                    content="test",
                    task_type=self._task_type,
                )
                if result and "embedding" in result:
                    self._available = True
                    self._dimension = len(result["embedding"])
                    logger.info(f"Gemini embedding connected (legacy): {self._model} ({self._dimension}d)")
                    return
            except Exception as e:
                logger.warning(f"Legacy Gemini embedding failed: {e}")

        logger.warning("No Gemini embedding SDK available")

    def embed(self, text: str) -> Optional[np.ndarray]:
        if not text or not text.strip():
            return None
        try:
            if self._use_new_sdk:
                result = self._genai_client.models.embed_content(
                    model=self._model,
                    contents=text,
                    config=genai_types.EmbedContentConfig(
                        output_dimensionality=self._dimension,
                    ),
                )
                return np.array(result.embeddings[0].values, dtype=np.float32)
            else:
                result = genai.embed_content(
                    model=f"models/{self._model}",
                    content=text,
                    task_type=self._task_type,
                )
                return np.array(result["embedding"], dtype=np.float32)
        except Exception as e:
            logger.error(f"Embedding failed for text '{text[:50]}': {e}")
            return None

    def embed_batch(self, texts: list[str]) -> list[Optional[np.ndarray]]:
        return [self.embed(t) for t in texts]

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def available(self) -> bool:
        return self._available
