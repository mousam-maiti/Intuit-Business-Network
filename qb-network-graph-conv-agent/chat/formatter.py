"""
MCP tool results → UI blocks (chart, table, entities, scores, signals, actions).

Each format_* function takes the raw MCP tool result dict and returns
partial WSResponse fields to merge with the Gemini response.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def format_search_entities(result: dict) -> dict:
    """search_entities → entity cards + table."""
    results = result.get("results", [])
    if not results:
        return {}

    entities = [r["golden_record_id"] for r in results if r.get("golden_record_id")]

    headers = ["Entity", "State", "Industry", "Confidence", "Sources"]
    rows = []
    for r in results:
        rows.append([
            r.get("canonical_name", ""),
            r.get("state", ""),
            r.get("naics_sector", r.get("naics_code", "")),
            f"{r.get('confidence', 0):.0%}",
            str(r.get("source_count", 1)),
        ])

    blocks: dict[str, Any] = {"entities": entities, "table": {"headers": headers, "rows": rows}}
    return blocks


def format_describe_entity(result: dict) -> dict:
    """describe_entity → scores + signals."""
    entity = result.get("entity")
    if not entity:
        return {}

    blocks: dict[str, Any] = {"entities": [entity["golden_record_id"]]}

    # Scores
    scores = []
    if entity.get("confidence") is not None:
        scores.append({"label": "Confidence", "value": entity["confidence"]})
    blocks["scores"] = scores

    # Signals
    signals = []
    if entity.get("status") == "merged":
        signals.append({"icon": "neutral", "text": f"Merged into {entity.get('merged_into', 'unknown')}"})
    if entity.get("source_count", 1) >= 5:
        signals.append({"icon": "positive", "text": f"Well-sourced: {entity['source_count']} source records"})
    elif entity.get("source_count", 1) == 1:
        signals.append({"icon": "negative", "text": "Single source record"})

    neighbor_count = result.get("neighbor_count", 0)
    if neighbor_count > 0:
        signals.append({"icon": "positive", "text": f"{neighbor_count} network connections"})
    elif result.get("kg_available"):
        signals.append({"icon": "neutral", "text": "No network connections found"})

    blocks["signals"] = signals

    # Actions
    blocks["actions"] = [
        {"label": "View in network", "action": "navigate", "payload": {"page": "network"}},
        {"label": "Show connections", "action": "select_entity",
         "payload": {"entityId": entity["golden_record_id"]}},
    ]

    return blocks


def format_query_network(result: dict) -> dict:
    """query_network → connection table + entities."""
    nodes = result.get("nodes", [])
    edges = result.get("edges", [])
    if not nodes:
        return {}

    entities = [n["entity_id"] for n in nodes if n.get("entity_id")]

    headers = ["Source", "Target", "Relationship"]
    rows = []
    for e in edges:
        rows.append([
            e.get("source", ""),
            e.get("target_name") or e.get("target", ""),
            e.get("relationship", "transactsWith"),
        ])

    blocks: dict[str, Any] = {"entities": entities}
    if rows:
        blocks["table"] = {"headers": headers, "rows": rows}

    # Signals
    signals = []
    node_count = result.get("node_count", len(nodes))
    edge_count = result.get("edge_count", len(edges))
    signals.append({"icon": "neutral", "text": f"Network: {node_count} entities, {edge_count} connections"})
    blocks["signals"] = signals

    blocks["actions"] = [
        {"label": "View in network", "action": "navigate", "payload": {"page": "network"}},
    ]

    return blocks


def format_aggregate_stats(result: dict) -> dict:
    """aggregate_stats → bar/pie chart + table."""
    groups = result.get("groups", [])
    if not groups:
        return {}

    group_by = result.get("group_by", "group")
    total = result.get("total", 0)

    # Chart
    chart_data = []
    for g in groups[:15]:  # Limit chart to 15 entries
        chart_data.append({
            "name": str(g.get("group_value", "")),
            "value": g.get("count", 0),
        })

    chart_type = "pie" if len(groups) <= 6 else "bar"
    chart = {
        "type": chart_type,
        "title": f"ENTITIES BY {group_by.upper().replace('_', ' ')}",
        "data": chart_data,
    }

    # Table
    headers = [group_by.replace("_", " ").title(), "Count", "% of Total"]
    rows = []
    for g in groups:
        count = g.get("count", 0)
        pct = f"{count / total * 100:.1f}%" if total > 0 else "0%"
        rows.append([str(g.get("group_value", "")), str(count), pct])

    blocks: dict[str, Any] = {
        "chart": chart,
        "table": {"headers": headers, "rows": rows},
    }
    return blocks


def format_search_by_relationship(result: dict) -> dict:
    """search_by_relationship → entity cards + table."""
    related = result.get("related_entities", [])
    if not related:
        return {}

    entities = [r["entity_id"] for r in related if r.get("entity_id")]

    headers = ["Entity", "State", "Industry", "Confidence"]
    rows = []
    for r in related:
        rows.append([
            r.get("canonical_name", r.get("name", "")),
            r.get("state", ""),
            r.get("naics_code", ""),
            f"{r.get('confidence', 0):.0%}" if r.get("confidence") else "",
        ])

    blocks: dict[str, Any] = {"entities": entities, "table": {"headers": headers, "rows": rows}}
    return blocks


def format_get_merge_history(result: dict) -> dict:
    """get_merge_history → audit table + signals."""
    records = result.get("audit_records", [])
    summary = result.get("summary", {})

    # Table
    headers = ["Decision", "Record ID", "Score", "Timestamp"]
    rows = []
    for r in records[:20]:  # Limit to 20 rows
        rows.append([
            r.get("decision", ""),
            r.get("record_id", r.get("orphan_record_id", "")),
            f"{r.get('final_score', 0):.0%}" if r.get("final_score") else "",
            str(r.get("created_at", "")),
        ])

    blocks: dict[str, Any] = {}
    if rows:
        blocks["table"] = {"headers": headers, "rows": rows}

    # Signals
    signals = []
    merge_count = summary.get("merges", 0)
    review_count = summary.get("reviews", 0)
    new_count = summary.get("new_entities", 0)
    if merge_count:
        signals.append({"icon": "positive", "text": f"{merge_count} merge(s) performed"})
    if review_count:
        signals.append({"icon": "neutral", "text": f"{review_count} review(s) pending or resolved"})
    if new_count:
        signals.append({"icon": "neutral", "text": f"{new_count} new entity creation(s)"})
    if not records:
        signals.append({"icon": "neutral", "text": "No merge history found"})
    blocks["signals"] = signals

    return blocks


# Dispatcher
_FORMATTERS = {
    "search_entities": format_search_entities,
    "describe_entity": format_describe_entity,
    "query_network": format_query_network,
    "aggregate_stats": format_aggregate_stats,
    "search_by_relationship": format_search_by_relationship,
    "get_merge_history": format_get_merge_history,
}


def format_tool_result(tool_name: str, result: dict) -> dict:
    """Format an MCP tool result into UI blocks."""
    formatter = _FORMATTERS.get(tool_name)
    if not formatter:
        return {}
    try:
        return formatter(result)
    except Exception as e:
        logger.warning(f"Formatter error for {tool_name}: {e}")
        return {}


def merge_blocks(gemini_blocks: dict, formatter_blocks: dict) -> dict:
    """Merge Gemini's JSON response with formatter-generated blocks.

    Gemini's content wins. Formatter fills gaps for entities, table, chart,
    scores, signals, actions.
    """
    merged = {**formatter_blocks}

    for key, value in gemini_blocks.items():
        if value is not None:
            if key == "entities" and key in merged:
                # Merge entity lists, dedup
                existing = set(merged.get("entities", []))
                existing.update(value)
                merged["entities"] = list(existing)
            else:
                merged[key] = value

    return merged
