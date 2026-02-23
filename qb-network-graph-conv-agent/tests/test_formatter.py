"""Tests for ResponseFormatter."""
import pytest

from chat.formatter import (
    format_search_entities,
    format_describe_entity,
    format_query_network,
    format_aggregate_stats,
    format_search_by_relationship,
    format_get_merge_history,
    format_tool_result,
    merge_blocks,
)


class TestFormatSearchEntities:
    def test_basic(self):
        result = {
            "results": [
                {"golden_record_id": "gr-001", "canonical_name": "Test Corp",
                 "state": "TX", "naics_sector": "Construction", "confidence": 0.92,
                 "source_count": 3},
                {"golden_record_id": "gr-002", "canonical_name": "Acme Inc",
                 "state": "CA", "naics_sector": "Manufacturing", "confidence": 0.85,
                 "source_count": 2},
            ],
            "total_found": 2,
        }
        blocks = format_search_entities(result)
        assert blocks["entities"] == ["gr-001", "gr-002"]
        assert blocks["table"]["headers"][0] == "Entity"
        assert len(blocks["table"]["rows"]) == 2
        assert blocks["table"]["rows"][0][0] == "Test Corp"

    def test_empty_results(self):
        assert format_search_entities({"results": []}) == {}


class TestFormatDescribeEntity:
    def test_basic(self):
        result = {
            "entity": {
                "golden_record_id": "gr-001", "canonical_name": "Test Corp",
                "confidence": 0.92, "status": "active", "source_count": 5,
            },
            "neighbors": [], "neighbor_count": 3, "kg_available": True,
        }
        blocks = format_describe_entity(result)
        assert "gr-001" in blocks["entities"]
        assert blocks["scores"][0]["label"] == "Confidence"
        assert blocks["scores"][0]["value"] == 0.92
        assert any("Well-sourced" in s["text"] for s in blocks["signals"])
        assert any("3 network connections" in s["text"] for s in blocks["signals"])
        assert len(blocks["actions"]) == 2

    def test_merged_entity(self):
        result = {
            "entity": {
                "golden_record_id": "gr-001", "canonical_name": "Test Corp",
                "confidence": 0.7, "status": "merged", "merged_into": "gr-100",
                "source_count": 1,
            },
            "neighbors": [], "neighbor_count": 0, "kg_available": True,
        }
        blocks = format_describe_entity(result)
        assert any("Merged into" in s["text"] for s in blocks["signals"])
        assert any("Single source" in s["text"] for s in blocks["signals"])

    def test_no_entity(self):
        assert format_describe_entity({"entity": None}) == {}


class TestFormatQueryNetwork:
    def test_basic(self):
        result = {
            "nodes": [
                {"entity_id": "gr-001", "canonical_name": "Root", "depth": 0},
                {"entity_id": "gr-002", "canonical_name": "Vendor", "depth": 1},
            ],
            "edges": [
                {"source": "gr-001", "target": "gr-002", "target_name": "Vendor",
                 "relationship": "transactsWith"},
            ],
            "node_count": 2, "edge_count": 1,
        }
        blocks = format_query_network(result)
        assert set(blocks["entities"]) == {"gr-001", "gr-002"}
        assert blocks["table"]["rows"][0] == ["gr-001", "Vendor", "transactsWith"]

    def test_empty(self):
        assert format_query_network({"nodes": [], "edges": []}) == {}


class TestFormatAggregateStats:
    def test_basic(self):
        result = {
            "groups": [
                {"group_value": "TX", "count": 50},
                {"group_value": "CA", "count": 30},
            ],
            "total": 80, "group_by": "state",
        }
        blocks = format_aggregate_stats(result)
        assert blocks["chart"]["type"] == "pie"  # <= 6 groups
        assert blocks["chart"]["data"][0] == {"name": "TX", "value": 50}
        assert blocks["table"]["rows"][0] == ["TX", "50", "62.5%"]

    def test_many_groups_uses_bar(self):
        groups = [{"group_value": f"G{i}", "count": i} for i in range(10)]
        result = {"groups": groups, "total": sum(range(10)), "group_by": "industry"}
        blocks = format_aggregate_stats(result)
        assert blocks["chart"]["type"] == "bar"


class TestFormatSearchByRelationship:
    def test_basic(self):
        result = {
            "related_entities": [
                {"entity_id": "gr-002", "canonical_name": "Vendor A",
                 "state": "TX", "naics_code": "238220", "confidence": 0.88},
            ],
        }
        blocks = format_search_by_relationship(result)
        assert blocks["entities"] == ["gr-002"]
        assert blocks["table"]["rows"][0][0] == "Vendor A"


class TestFormatGetMergeHistory:
    def test_basic(self):
        result = {
            "audit_records": [
                {"decision": "MERGE", "record_id": "rec-001",
                 "final_score": 0.91, "created_at": "2026-01-15"},
            ],
            "summary": {"merges": 1, "reviews": 0, "new_entities": 0},
        }
        blocks = format_get_merge_history(result)
        assert blocks["table"]["rows"][0][0] == "MERGE"
        assert any("1 merge" in s["text"] for s in blocks["signals"])

    def test_empty_history(self):
        result = {"audit_records": [], "summary": {"merges": 0, "reviews": 0, "new_entities": 0}}
        blocks = format_get_merge_history(result)
        assert any("No merge history" in s["text"] for s in blocks["signals"])


class TestMergeBlocks:
    def test_gemini_content_wins(self):
        gemini = {"content": "Gemini says this", "entities": ["e1"]}
        formatter = {"content": "Formatter default", "entities": ["e2"], "chart": {"type": "bar"}}
        merged = merge_blocks(gemini, formatter)
        assert merged["content"] == "Gemini says this"
        assert set(merged["entities"]) == {"e1", "e2"}
        assert merged["chart"]["type"] == "bar"

    def test_formatter_fills_gaps(self):
        gemini = {"content": "Answer"}
        formatter = {"table": {"headers": ["A"], "rows": [["1"]]}, "entities": ["e1"]}
        merged = merge_blocks(gemini, formatter)
        assert merged["content"] == "Answer"
        assert merged["table"]["headers"] == ["A"]
        assert merged["entities"] == ["e1"]

    def test_dispatch(self):
        result = {"results": [{"golden_record_id": "g1", "canonical_name": "X",
                               "state": "TX", "confidence": 0.9, "source_count": 1}],
                  "total_found": 1}
        blocks = format_tool_result("search_entities", result)
        assert "entities" in blocks

    def test_unknown_tool(self):
        assert format_tool_result("unknown_tool", {}) == {}
