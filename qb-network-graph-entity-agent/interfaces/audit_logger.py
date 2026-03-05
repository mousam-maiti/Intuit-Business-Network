from __future__ import annotations

"""Abstract interface for decision audit logging."""
from abc import ABC, abstractmethod


class AbstractAuditLogger(ABC):
    """Logs resolution decisions for audit trail."""

    @abstractmethod
    async def log_decision(
        self,
        event_id: str,
        record_id: str,
        decision: str,
        target_golden_record_id: str | None,
        confidence: float,
        dimension_scores: dict,
        reasoning: str,
        key_factors: list[str],
        evaluation_chain: list[dict],
        agent_metadata: dict,
    ) -> None:
        """Log a resolution decision to the audit trail."""
        ...
