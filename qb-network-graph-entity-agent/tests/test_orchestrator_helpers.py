"""
Tests for orchestrator module-level helper functions.
"""
import pytest
from models.resolution import (
    CandidateMatch, ComparisonResult, DimensionResult,
    DimensionConfidence, DimensionScores, SimilarityResult, MatchLevel,
)
from orchestrator import _ensure_list, _ensure_dict, _extract_dim_scores, _build_key_factors


# ══════════════════════════════════════════════════════════════
# TestEnsureList
# ══════════════════════════════════════════════════════════════

class TestEnsureList:
    def test_list_passthrough(self):
        assert _ensure_list(["a", "b"]) == ["a", "b"]

    def test_json_string(self):
        assert _ensure_list('["a", "b"]') == ["a", "b"]

    def test_plain_string(self):
        assert _ensure_list("hello") == ["hello"]

    def test_invalid_json(self):
        assert _ensure_list("{not valid") == ["{not valid"]

    def test_empty_string(self):
        assert _ensure_list("") == []

    def test_non_list_type(self):
        assert _ensure_list(42) == []


# ══════════════════════════════════════════════════════════════
# TestEnsureDict
# ══════════════════════════════════════════════════════════════

class TestEnsureDict:
    def test_dict_passthrough(self):
        assert _ensure_dict({"a": 1}) == {"a": 1}

    def test_json_string(self):
        assert _ensure_dict('{"a": 1}') == {"a": 1}

    def test_invalid_json(self):
        assert _ensure_dict("not json{") == {}

    def test_non_dict_type(self):
        assert _ensure_dict(42) == {}


# ══════════════════════════════════════════════════════════════
# TestExtractDimScores
# ══════════════════════════════════════════════════════════════

class TestExtractDimScores:
    def test_with_comparison(self):
        cm = CandidateMatch(
            golden_record_id="G-001",
            canonical_name="TEST",
            comparison=ComparisonResult(
                identity=DimensionResult(score=0.9, confidence=DimensionConfidence.HIGH),
                industry=DimensionResult(score=0.8, confidence=DimensionConfidence.HIGH),
                location=DimensionResult(score=0.7, confidence=DimensionConfidence.MEDIUM),
                commodity=DimensionResult(score=0.6, confidence=DimensionConfidence.MEDIUM),
                behavioral=DimensionResult(score=0.5, confidence=DimensionConfidence.LOW),
            ),
        )
        scores = _extract_dim_scores(cm)
        assert isinstance(scores, DimensionScores)
        assert scores.identity == 0.9
        assert scores.industry == 0.8
        assert scores.location == 0.7
        assert scores.commodity == 0.6
        assert scores.behavioral == 0.5

    def test_without_comparison(self):
        cm = CandidateMatch(golden_record_id="G-001", canonical_name="TEST")
        scores = _extract_dim_scores(cm)
        assert scores.identity == 0.0
        assert scores.industry == 0.0


# ══════════════════════════════════════════════════════════════
# TestBuildKeyFactors
# ══════════════════════════════════════════════════════════════

class TestBuildKeyFactors:
    def _make_cm(self, identity_score=0.0, ein_match=None, industry_score=0.0,
                 ontology=False, location_score=0.0, commodity_score=0.0,
                 similarity_composite=0.0):
        identity_details = {}
        if ein_match:
            identity_details["ein_match"] = ein_match
        industry_details = {}
        if ontology:
            industry_details["ontology_consulted"] = True

        comparison = ComparisonResult(
            identity=DimensionResult(score=identity_score, confidence=DimensionConfidence.HIGH, details=identity_details),
            industry=DimensionResult(score=industry_score, confidence=DimensionConfidence.HIGH, details=industry_details),
            location=DimensionResult(score=location_score, confidence=DimensionConfidence.MEDIUM),
            commodity=DimensionResult(score=commodity_score, confidence=DimensionConfidence.MEDIUM),
        )
        similarity = SimilarityResult(composite_similarity=similarity_composite) if similarity_composite else None

        return CandidateMatch(
            golden_record_id="G-001",
            canonical_name="TEST",
            comparison=comparison,
            similarity=similarity,
        )

    def test_strong_identity(self):
        cm = self._make_cm(identity_score=0.85)
        factors = _build_key_factors(cm)
        assert "strong_identity_match" in factors

    def test_ein_exact(self):
        cm = self._make_cm(ein_match="EXACT")
        factors = _build_key_factors(cm)
        assert "EIN_exact" in factors

    def test_ontology(self):
        cm = self._make_cm(industry_score=0.5, ontology=True)
        factors = _build_key_factors(cm)
        assert "ontology_cross_taxonomy" in factors

    def test_same_location(self):
        cm = self._make_cm(location_score=0.8)
        factors = _build_key_factors(cm)
        assert "same_location" in factors

    def test_commodity_overlap(self):
        cm = self._make_cm(commodity_score=0.6)
        factors = _build_key_factors(cm)
        assert any("commodity_overlap" in f for f in factors)

    def test_strong_semantic_similarity(self):
        cm = self._make_cm(similarity_composite=0.85)
        factors = _build_key_factors(cm)
        assert "strong_semantic_similarity" in factors
