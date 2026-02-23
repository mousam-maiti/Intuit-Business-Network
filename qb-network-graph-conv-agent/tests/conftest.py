"""
Shared fixtures for conversational agent tests.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from clients.chat_db import MockChatDB
from chat.session import SessionManager
from chat.context import ContextWindow
from config import ContextConfig


@pytest.fixture
def mock_db():
    """In-memory chat database."""
    db = MockChatDB()
    return db


@pytest.fixture
def session_mgr(mock_db):
    """SessionManager backed by MockChatDB."""
    return SessionManager(mock_db)


@pytest.fixture
def context_config():
    """Default context config for tests."""
    return ContextConfig(max_messages=10, keep_recent=3, max_tool_calls=5)


@pytest.fixture
def context_window(mock_db, context_config):
    """ContextWindow backed by MockChatDB."""
    return ContextWindow(mock_db, context_config)


class MockMCPClient:
    """Mock MCP client that returns canned tool results."""

    def __init__(self):
        self.connected = True
        self._tool_names = [
            "search_entities", "describe_entity", "query_network",
            "aggregate_stats", "search_by_relationship", "get_merge_history",
        ]
        self._call_log: list[tuple[str, dict]] = []
        self._responses: dict[str, dict] = {}

    def set_response(self, tool_name: str, response: dict):
        self._responses[tool_name] = response

    async def connect(self):
        pass

    async def call_tool(self, name: str, arguments: dict):
        self._call_log.append((name, arguments))
        if name in self._responses:
            return self._responses[name]
        # Default responses
        defaults = {
            "search_entities": {
                "results": [
                    {"golden_record_id": "gr-001", "canonical_name": "Test Corp",
                     "state": "TX", "naics_code": "236220", "naics_sector": "Construction",
                     "confidence": 0.92, "source_count": 3, "entity_type": "business"},
                ],
                "total_found": 1, "query": arguments.get("query", ""),
            },
            "describe_entity": {
                "entity": {
                    "golden_record_id": arguments.get("entity_id", "gr-001"),
                    "canonical_name": "Test Corp", "confidence": 0.92,
                    "status": "active", "source_count": 3,
                },
                "neighbors": [], "neighbor_count": 0, "kg_available": True,
            },
            "query_network": {
                "nodes": [
                    {"entity_id": "gr-001", "canonical_name": "Test Corp", "depth": 0},
                    {"entity_id": "gr-002", "canonical_name": "Vendor A", "depth": 1},
                ],
                "edges": [
                    {"source": "gr-001", "target": "gr-002", "relationship": "transactsWith",
                     "target_name": "Vendor A"},
                ],
                "node_count": 2, "edge_count": 1, "depth_reached": 1,
            },
            "aggregate_stats": {
                "groups": [
                    {"group_value": "TX", "count": 50},
                    {"group_value": "CA", "count": 30},
                ],
                "total": 80, "group_by": arguments.get("group_by", "state"),
            },
            "search_by_relationship": {
                "related_entities": [
                    {"entity_id": "gr-002", "canonical_name": "Vendor A",
                     "state": "TX", "naics_code": "238220", "confidence": 0.88},
                ],
                "count": 1, "source_entity": arguments.get("entity_id", ""),
                "relationship_type": arguments.get("relationship_type", "transactsWith"),
            },
            "get_merge_history": {
                "entity_id": arguments.get("entity_id", ""),
                "audit_records": [
                    {"decision": "MERGE", "record_id": "rec-001",
                     "final_score": 0.91, "created_at": "2026-01-15T10:00:00"},
                ],
                "total_records": 1,
                "summary": {"merges": 1, "reviews": 0, "new_entities": 0},
            },
        }
        return defaults.get(name, {})

    async def close(self):
        self.connected = False


@pytest.fixture
def mock_mcp():
    """Mock MCP client."""
    return MockMCPClient()
