from __future__ import annotations

"""MCP-backed audit logger — calls log_decision tool on MCP server."""
from interfaces.audit_logger import AbstractAuditLogger
from clients.mcp_client import MCPToolClient


class MCPAuditLogger(AbstractAuditLogger):
    """Logs resolution decisions via MCP server's log_decision tool."""

    def __init__(self, mcp: MCPToolClient):
        self._mcp = mcp

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
        await self._mcp.call_tool("log_decision", {
            "event_id": event_id,
            "record_id": record_id,
            "decision": decision,
            "target_golden_record_id": target_golden_record_id,
            "confidence": confidence,
            "dimension_scores": dimension_scores,
            "reasoning": reasoning,
            "key_factors": key_factors,
            "evaluation_chain": evaluation_chain,
            "agent_metadata": agent_metadata,
        })
