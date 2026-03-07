"""
Tests for clients/llm_client.py — mocks genai.GenerativeModel.generate_content.
"""
import json
import pytest
from unittest.mock import MagicMock, patch
from config import LLMConfig
from clients.llm_client import LLMClient


@pytest.fixture
def unavailable_llm():
    c = LLMClient(LLMConfig())
    c._available = False
    return c


@pytest.fixture
def available_llm():
    c = LLMClient(LLMConfig())
    c._available = True
    c._model = MagicMock()
    c._ambiguous_model = MagicMock()
    return c


def _mock_response(text):
    """Build a mock Gemini response with given text."""
    part = MagicMock()
    part.text = text
    content = MagicMock()
    content.parts = [part]
    candidate = MagicMock()
    candidate.content = content
    candidate.finish_reason = "STOP"
    resp = MagicMock()
    resp.candidates = [candidate]
    return resp


def _make_evidence(candidates=None):
    if candidates is None:
        candidates = [{"golden_record_id": "G-001", "canonical_name": "TEST CORP"}]
    return {
        "orphan_persona": {"identity": {"normalized_name": "TEST"}},
        "candidates": candidates,
        "evaluation_steps": ["find_candidates: score=0.7"],
    }


# ══════════════════════════════════════════════════════════════
# TestUnavailable
# ══════════════════════════════════════════════════════════════

class TestUnavailable:
    def test_available_false(self, unavailable_llm):
        assert unavailable_llm.available is False

    def test_reason_returns_fallback_review(self, unavailable_llm):
        result = unavailable_llm.reason(_make_evidence())
        assert result["decision"] == "REVIEW"
        assert result["fallback"] is True


# ══════════════════════════════════════════════════════════════
# TestBuildEvidencePrompt
# ══════════════════════════════════════════════════════════════

class TestBuildEvidencePrompt:
    def test_orphan_section(self, available_llm):
        evidence = _make_evidence()
        prompt = available_llm._build_evidence_prompt(evidence)
        assert "Orphan Record" in prompt
        assert "TEST" in prompt

    def test_candidates_section(self, available_llm):
        evidence = _make_evidence()
        prompt = available_llm._build_evidence_prompt(evidence)
        assert "Candidate 1" in prompt
        assert "TEST CORP" in prompt

    def test_evaluation_steps(self, available_llm):
        evidence = _make_evidence()
        prompt = available_llm._build_evidence_prompt(evidence)
        assert "Evaluation Steps" in prompt
        assert "find_candidates" in prompt

    def test_empty_candidates(self, available_llm):
        evidence = _make_evidence(candidates=[])
        prompt = available_llm._build_evidence_prompt(evidence)
        assert "(0 " in prompt or "0 remaining" in prompt or "Candidates" in prompt

    def test_comparison_and_similarity(self, available_llm):
        evidence = _make_evidence(candidates=[{
            "golden_record_id": "G-001",
            "canonical_name": "TEST CORP",
            "comparison": {"composite": 0.7},
            "similarity": {"name": 0.8},
        }])
        prompt = available_llm._build_evidence_prompt(evidence)
        assert "comparison" in prompt.lower()
        assert "similarity" in prompt.lower()


# ══════════════════════════════════════════════════════════════
# TestParseResponse
# ══════════════════════════════════════════════════════════════

class TestParseResponse:
    def test_valid_json_merge(self, available_llm):
        text = json.dumps({
            "decision": "MERGE",
            "target_golden_record_id": "G-001",
            "confidence": 0.92,
            "reasoning": "Strong match",
        })
        result = available_llm._parse_response(text)
        assert result["decision"] == "MERGE"
        assert result["confidence"] == 0.92

    def test_valid_json_review(self, available_llm):
        text = json.dumps({
            "decision": "REVIEW",
            "target_golden_record_id": "G-001",
            "confidence": 0.65,
            "reasoning": "Ambiguous",
        })
        result = available_llm._parse_response(text)
        assert result["decision"] == "REVIEW"

    def test_valid_json_new_entity(self, available_llm):
        text = json.dumps({
            "decision": "NEW_ENTITY",
            "target_golden_record_id": None,
            "confidence": 0.3,
            "reasoning": "No match",
        })
        result = available_llm._parse_response(text)
        assert result["decision"] == "NEW_ENTITY"

    def test_strips_markdown_fences(self, available_llm):
        text = '```json\n{"decision": "MERGE", "confidence": 0.9, "reasoning": "test"}\n```'
        result = available_llm._parse_response(text)
        assert result["decision"] == "MERGE"

    def test_invalid_json(self, available_llm):
        result = available_llm._parse_response("this is not json at all")
        assert result["decision"] == "REVIEW"
        assert result.get("parse_error") is True

    def test_missing_decision(self, available_llm):
        text = json.dumps({"confidence": 0.9})
        result = available_llm._parse_response(text)
        assert result["decision"] == "REVIEW"
        assert result.get("parse_error") is True

    def test_invalid_decision(self, available_llm):
        text = json.dumps({"decision": "INVALID", "confidence": 0.9})
        result = available_llm._parse_response(text)
        assert result["decision"] == "REVIEW"
        assert result.get("parse_error") is True

    def test_missing_confidence(self, available_llm):
        text = json.dumps({"decision": "MERGE"})
        result = available_llm._parse_response(text)
        assert result["decision"] == "REVIEW"
        assert result.get("parse_error") is True


# ══════════════════════════════════════════════════════════════
# TestFallbackReview
# ══════════════════════════════════════════════════════════════

class TestFallbackReview:
    def test_returns_fallback_decision(self, available_llm):
        result = available_llm._fallback_review(_make_evidence(), "test reason")
        assert result["decision"] == "REVIEW"
        assert result["confidence"] == 0.50

    def test_best_candidate_target(self, available_llm):
        result = available_llm._fallback_review(_make_evidence(), "unavailable")
        assert result["target_golden_record_id"] == "G-001"

    def test_empty_candidates(self, available_llm):
        evidence = _make_evidence(candidates=[])
        result = available_llm._fallback_review(evidence, "no candidates")
        # With empty candidates, best = {} so target is {}.get("golden_record_id") = None
        assert result["target_golden_record_id"] is None

    def test_fallback_flag(self, available_llm):
        result = available_llm._fallback_review(_make_evidence(), "test")
        assert result["fallback"] is True


# ══════════════════════════════════════════════════════════════
# TestReasonErrors
# ══════════════════════════════════════════════════════════════

class TestReasonErrors:
    def test_timeout_error(self, available_llm):
        available_llm._ambiguous_model.generate_content.side_effect = TimeoutError("timeout")
        result = available_llm.reason(_make_evidence())
        assert result["decision"] == "REVIEW"
        assert result["fallback"] is True

    def test_generic_exception(self, available_llm):
        available_llm._ambiguous_model.generate_content.side_effect = RuntimeError("API error")
        result = available_llm.reason(_make_evidence())
        assert result["decision"] == "REVIEW"
        assert result["fallback"] is True

    def test_empty_response_no_parts(self, available_llm):
        candidate = MagicMock()
        candidate.content.parts = []
        candidate.finish_reason = "SAFETY"
        resp = MagicMock()
        resp.candidates = [candidate]
        available_llm._ambiguous_model.generate_content.return_value = resp
        result = available_llm.reason(_make_evidence())
        assert result["decision"] == "REVIEW"
        assert result["fallback"] is True
