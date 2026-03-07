from __future__ import annotations

"""MCP-backed candidate finder — calls find_candidates tool on MCP server."""
from interfaces.candidate_finder import AbstractCandidateFinder
from clients.mcp_client import MCPToolClient


class MCPCandidateFinder(AbstractCandidateFinder):
    """Finds candidate golden records via the MCP server's find_candidates tool."""

    def __init__(self, mcp: MCPToolClient):
        self._mcp = mcp

    async def find(self, orphan_persona: dict, max_candidates: int = 20) -> dict:
        return await self._mcp.call_tool("find_candidates", {
            "orphan_persona": orphan_persona,
            "max_candidates": max_candidates,
        })
