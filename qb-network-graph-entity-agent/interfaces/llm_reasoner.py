from __future__ import annotations

"""Abstract interface for LLM-based reasoning."""
from abc import ABC, abstractmethod


class AbstractLLMReasoner(ABC):
    """LLM reasoning for ambiguous entity resolution cases."""

    @abstractmethod
    def reason(self, evidence: dict) -> dict:
        """Evaluate evidence and make a resolution decision.

        Args:
            evidence: dict with keys:
                orphan_persona: dict
                candidates: list of candidate evidence dicts
                evaluation_steps: list of step summaries

        Returns:
            dict with keys: decision, target_golden_record_id, confidence,
            reasoning, key_factors, key_uncertainty, llm_duration_ms, model_used.
        """
        ...

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether the LLM client is connected and available."""
        ...
