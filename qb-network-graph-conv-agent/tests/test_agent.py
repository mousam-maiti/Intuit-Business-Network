"""Tests for ConversationalAgent (mocked — no real LLM calls)."""
import json
import pytest

from chat.agent import ConversationalAgent
from chat.prompts import TOOL_LABELS


class TestParseResponse:
    def test_json_response(self):
        text = json.dumps({"content": "Found 5 entities", "entities": ["e1", "e2"]})
        result = ConversationalAgent._parse_response(text)
        assert result["content"] == "Found 5 entities"
        assert result["entities"] == ["e1", "e2"]

    def test_json_in_code_block(self):
        text = '```json\n{"content": "Hello"}\n```'
        result = ConversationalAgent._parse_response(text)
        assert result["content"] == "Hello"

    def test_plain_text_fallback(self):
        text = "This is a plain text response."
        result = ConversationalAgent._parse_response(text)
        assert result["content"] == text

    def test_empty_string(self):
        result = ConversationalAgent._parse_response("")
        assert result["content"] == ""

    def test_json_without_content_field(self):
        text = json.dumps({"answer": "No content key"})
        result = ConversationalAgent._parse_response(text)
        # Falls back to plain text since no "content" key
        assert result["content"] == text


class TestAgentInit:
    def test_init(self, mock_mcp):
        class MockLLM:
            model_name = "test-model"
            available = True
        agent = ConversationalAgent(
            mcp=mock_mcp, llm=MockLLM(),
            max_iterations=8,
        )
        assert agent.llm.model_name == "test-model"
        assert agent.max_iterations == 8
