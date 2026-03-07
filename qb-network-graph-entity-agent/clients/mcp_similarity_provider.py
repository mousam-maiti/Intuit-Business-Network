from __future__ import annotations

"""MCP-backed similarity provider — calls semantic_similarity tool on MCP server."""
from interfaces.similarity_provider import AbstractSimilarityProvider
from clients.mcp_client import MCPToolClient


class MCPSimilarityProvider(AbstractSimilarityProvider):
    """Semantic similarity via the MCP server's semantic_similarity tool."""

    def __init__(self, mcp: MCPToolClient):
        self._mcp = mcp

    async def compute(self, orphan_persona: dict, candidate: dict) -> dict:
        return await self._mcp.call_tool("semantic_similarity", {
            "orphan_persona": orphan_persona,
            "candidate": candidate,
        })
