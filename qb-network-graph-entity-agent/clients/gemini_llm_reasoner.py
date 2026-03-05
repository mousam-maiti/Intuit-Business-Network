from __future__ import annotations

"""Gemini LLM reasoner — wraps LLMClient to implement AbstractLLMReasoner."""
from interfaces.llm_reasoner import AbstractLLMReasoner
from clients.llm_client import LLMClient
from config import LLMConfig


class GeminiLLMReasoner(AbstractLLMReasoner):
    """LLM reasoning via Google Gemini, delegating to LLMClient."""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def reason(self, evidence: dict) -> dict:
        return self._llm.reason(evidence)

    @property
    def available(self) -> bool:
        return self._llm.available
