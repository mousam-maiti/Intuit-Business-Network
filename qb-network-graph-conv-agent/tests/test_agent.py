"""Tests for ConversationalAgent (mocked — no real Gemini calls)."""
import json
import pytest

from chat.agent import ConversationalAgent, _map_type
from chat.prompts import TOOL_DECLARATIONS, TOOL_LABELS


class TestToolDeclarations:
    def test_all_six_tools_declared(self):
        names = {td["name"] for td in TOOL_DECLARATIONS}
        assert names == {
            "search_entities", "describe_entity", "query_network",
            "aggregate_stats", "search_by_relationship", "get_merge_history",
        }

    def test_all_tools_have_labels(self):
        for td in TOOL_DECLARATIONS:
            assert td["name"] in TOOL_LABELS

    def test_declarations_have_required_fields(self):
        for td in TOOL_DECLARATIONS:
            assert "name" in td
            assert "description" in td
            assert "parameters" in td
            assert "properties" in td["parameters"]
            assert "required" in td["parameters"]
            assert len(td["parameters"]["required"]) >= 1


class TestMapType:
    def test_string(self):
        import google.generativeai as genai
        assert _map_type("string") == genai.protos.Type.STRING

    def test_integer(self):
        import google.generativeai as genai
        assert _map_type("integer") == genai.protos.Type.INTEGER

    def test_number(self):
        import google.generativeai as genai
        assert _map_type("number") == genai.protos.Type.NUMBER

    def test_unknown_defaults_to_string(self):
        import google.generativeai as genai
        assert _map_type("foobar") == genai.protos.Type.STRING


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


class TestBuildTools:
    def test_builds_without_error(self):
        tools = ConversationalAgent._build_tools()
        assert len(tools) == 1  # Single Tool proto with all declarations
        func_decls = tools[0].function_declarations
        assert len(func_decls) == 6


class TestAgentInit:
    def test_init(self, mock_mcp):
        agent = ConversationalAgent(
            mcp=mock_mcp, llm_model="gemini-2.5-flash",
            temperature=0.3, max_tool_calls=5,
        )
        assert agent.llm_model == "gemini-2.5-flash"
        assert agent.max_tool_calls == 5
