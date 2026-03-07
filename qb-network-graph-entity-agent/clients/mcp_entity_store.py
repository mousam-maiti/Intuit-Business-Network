from __future__ import annotations

"""MCP-backed entity store — calls golden record tools on MCP server."""
from interfaces.entity_store import AbstractEntityStore
from clients.mcp_client import MCPToolClient


class MCPEntityStore(AbstractEntityStore):
    """Golden record operations via MCP server tools."""

    def __init__(self, mcp: MCPToolClient):
        self._mcp = mcp

    async def merge(
        self,
        orphan_record_id: str,
        orphan_persona: dict,
        golden_record_id: str,
        merge_reasoning: dict,
        company_id: str,
        record_type: str = "vendor",
    ) -> dict:
        return await self._mcp.call_tool("merge_into_golden_record", {
            "orphan_record_id": orphan_record_id,
            "orphan_persona": orphan_persona,
            "golden_record_id": golden_record_id,
            "merge_reasoning": merge_reasoning,
            "company_id": company_id,
            "record_type": record_type,
        })

    async def create(
        self,
        orphan_record_id: str,
        orphan_persona: dict,
        creation_reasoning: dict,
        company_id: str,
        record_type: str = "vendor",
    ) -> dict:
        return await self._mcp.call_tool("create_golden_record", {
            "orphan_record_id": orphan_record_id,
            "orphan_persona": orphan_persona,
            "creation_reasoning": creation_reasoning,
            "company_id": company_id,
            "record_type": record_type,
        })

    async def submit_for_review(
        self,
        orphan_record_id: str,
        orphan_persona: dict,
        candidate_golden_record_id: str,
        review_reasoning: dict,
        company_id: str,
        record_type: str = "vendor",
    ) -> dict:
        return await self._mcp.call_tool("submit_for_review", {
            "orphan_record_id": orphan_record_id,
            "orphan_persona": orphan_persona,
            "candidate_golden_record_id": candidate_golden_record_id,
            "review_reasoning": review_reasoning,
            "company_id": company_id,
            "record_type": record_type,
        })

    async def merge_golden_records(
        self,
        survivor_id: str,
        absorbed_id: str,
        merge_reasoning: dict,
    ) -> dict:
        return await self._mcp.call_tool("merge_golden_records", {
            "survivor_id": survivor_id,
            "absorbed_id": absorbed_id,
            "merge_reasoning": merge_reasoning,
        })

    async def describe(self, entity_id: str) -> dict:
        return await self._mcp.call_tool("describe_entity", {
            "entity_id": entity_id,
        })
