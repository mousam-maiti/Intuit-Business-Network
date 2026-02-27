"""
MCP tool results → UI blocks (chart, table, entities, scores, signals, actions).

The LLM decides what visual blocks to include in its Answer JSON.
The formatter only provides supplementary data that the LLM can't generate
(e.g., navigation actions). It does NOT auto-generate charts, tables, scores,
or signals — those are the LLM's responsibility.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def format_tool_result(tool_name: str, result: dict) -> dict:
    """Format an MCP tool result into supplementary UI blocks.

    Only generates navigation actions — all visual blocks (chart, table,
    scores, signals) are left to the LLM's Answer JSON.
    """
    try:
        # describe_entity → navigation actions
        if tool_name == "describe_entity":
            entity = result.get("entity")
            if entity and entity.get("golden_record_id"):
                return {
                    "actions": [
                        {"label": "View in network", "action": "navigate", "payload": {"page": "network"}},
                        {"label": "Show connections", "action": "select_entity",
                         "payload": {"entityId": entity["golden_record_id"], "name": entity.get("canonical_name", "")}},
                    ],
                }

        # query_network → navigation action
        if tool_name == "query_network" and result.get("nodes"):
            return {
                "actions": [
                    {"label": "View in network", "action": "navigate", "payload": {"page": "network"}},
                ],
            }

    except Exception as e:
        logger.warning(f"Formatter error for {tool_name}: {e}")

    return {}


def merge_blocks(gemini_blocks: dict, formatter_blocks: dict) -> dict:
    """Merge Gemini's JSON response with formatter-generated blocks.

    LLM is authoritative for all visual blocks. Formatter only fills in
    actions if the LLM didn't provide any.
    """
    merged = {**gemini_blocks}

    # Only use formatter actions if LLM didn't provide any
    if not merged.get("actions") and formatter_blocks.get("actions"):
        merged["actions"] = formatter_blocks["actions"]

    return merged
