from __future__ import annotations

"""MCP-backed field comparator — calls compare_fields tool on MCP server."""
from interfaces.field_comparator import AbstractFieldComparator
from clients.mcp_client import MCPToolClient


class MCPFieldComparator(AbstractFieldComparator):
    """Deterministic field comparison via the MCP server's compare_fields tool."""

    def __init__(self, mcp: MCPToolClient):
        self._mcp = mcp

    async def compare(self, orphan_persona: dict, candidate: dict) -> dict:
        return await self._mcp.call_tool("compare_fields", {
            "orphan_persona": orphan_persona,
            "candidate": candidate,
        })
