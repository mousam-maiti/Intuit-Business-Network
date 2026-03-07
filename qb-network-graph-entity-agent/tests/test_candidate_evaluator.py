"""
Tests for mcp/candidate_evaluator.py.
"""
import json
import pytest
from models.persona import ClassifiedPersona, IdentityDimension, IndustryDimension, LocationDimension, CommodityDimension
from models.resolution import ComparisonResult, SimilarityResult
from mcp.candidate_evaluator import (
    CandidateEvaluator, _parse_list, _parse_persona,
    _to_classified_persona, _persona_to_texts,
)


# ══════════════════════════════════════════════════════════════
# TestHelperFunctions
# ══════════════════════════════════════════════════════════════

class TestHelperFunctions:
    # _parse_list
    def test_parse_list_from_string(self):
        assert _parse_list('["a", "b"]') == ["a", "b"]

    def test_parse_list_from_list(self):
        assert _parse_list(["a", "b"]) == ["a", "b"]

    def test_parse_list_invalid_json(self):
        assert _parse_list("not json") == ["not json"]

    def test_parse_list_empty(self):
        assert _parse_list("") == []

    def test_parse_list_non_list(self):
        assert _parse_list(42) == []

    # _parse_persona
    def test_parse_persona_from_string(self):
        data = json.dumps({"identity": {"normalized_name": "TEST"}})
        result = _parse_persona(data)
        assert result["identity"]["normalized_name"] == "TEST"

    def test_parse_persona_from_dict(self):
        data = {"identity": {"normalized_name": "TEST"}}
        assert _parse_persona(data) == data

    def test_parse_persona_invalid(self):
        assert _parse_persona("not json{") == {}

    # _to_classified_persona
    def test_to_classified_persona_from_dict(self):
        data = {"identity": {"normalized_name": "FROM DICT"}}
        result = _to_classified_persona(data)
        assert isinstance(result, ClassifiedPersona)
        assert result.identity.normalized_name == "FROM DICT"

    def test_to_classified_persona_invalid(self):
        result = _to_classified_persona("not a dict")
        assert isinstance(result, ClassifiedPersona)
        assert result.identity.normalized_name == ""

    def test_to_classified_persona_passthrough(self):
        p = ClassifiedPersona(identity=IdentityDimension(normalized_name="PASS"))
        result = _to_classified_persona(p)
        assert result is p

    # _persona_to_texts
    def test_persona_to_texts_full(self):
        p = ClassifiedPersona(
            identity=IdentityDimension(normalized_name="BOBS PLUMBING", legal_suffix="LLC"),
            industry=IndustryDimension(naics_code="238220", commodity_keywords=["pvc"]),
            commodity=CommodityDimension(top_keywords=["pvc pipe", "copper"]),
            location=LocationDimension(city_norm="AUSTIN", state="TX", zip5="78701"),
        )
        texts = _persona_to_texts(p)
        assert "BOBS PLUMBING" in texts["name"]
        assert "LLC" in texts["name"]
        assert "238220" in texts["industry"]
        assert "pvc pipe" in texts["commodities"]
        assert "AUSTIN" in texts["location"]

    def test_persona_to_texts_sparse(self):
        p = ClassifiedPersona(identity=IdentityDimension(normalized_name="SPARSE"))
        texts = _persona_to_texts(p)
        assert "SPARSE" in texts["name"]
        assert texts["industry"] == ""
        assert texts["commodities"] == ""
        assert texts["location"] == ""


# ══════════════════════════════════════════════════════════════
# TestFindCandidates
# ══════════════════════════════════════════════════════════════

class TestFindCandidates:
    def test_no_candidates(self, mock_evaluator, persona_factory):
        persona = persona_factory()
        result = mock_evaluator.find_candidates(persona)
        assert result["candidates"] == []
        assert result["bucket_stats"]["total_buckets_checked"] > 0

    def test_sorted_by_bucket_overlap(self, mock_evaluator, persona_factory, golden_factory, mock_mysql):
        # Create two GRs: one matching 2 buckets, one matching 1
        gr1 = golden_factory(
            gr_id="G-multi", name="BOBS PLUMBING",
            bucket_keys=["name:BOBS+TX", "naics4:2382+TX"],
        )
        gr2 = golden_factory(
            gr_id="G-single", name="BOBS ELECTRIC",
            bucket_keys=["name:BOBS+TX"],
        )
        mock_mysql.write_golden_record(gr1)
        mock_mysql.write_golden_record(gr2)

        persona = persona_factory()
        result = mock_evaluator.find_candidates(persona)
        candidates = result["candidates"]
        if len(candidates) >= 2:
            # First candidate should have more bucket overlap
            first_buckets = len(candidates[0].get("matched_via_buckets", []))
            second_buckets = len(candidates[1].get("matched_via_buckets", []))
            assert first_buckets >= second_buckets

    def test_max_20_limit(self, mock_evaluator, persona_factory, golden_factory, mock_mysql):
        # Create 25 matching GRs
        for i in range(25):
            gr = golden_factory(
                gr_id=f"G-limit{i:03d}", name="BOBS PLUMBING",
                bucket_keys=["name:BOBS+TX"],
            )
            mock_mysql.write_golden_record(gr)

        persona = persona_factory()
        result = mock_evaluator.find_candidates(persona, max_candidates=20)
        assert len(result["candidates"]) <= 20

    def test_bucket_stats_populated(self, mock_evaluator, persona_factory):
        persona = persona_factory()
        result = mock_evaluator.find_candidates(persona)
        stats = result["bucket_stats"]
        assert "total_buckets_checked" in stats
        assert "total_candidates_before_dedup" in stats
        assert "total_candidates_after_dedup" in stats

    def test_hydration_skips_missing(self, mock_evaluator, persona_factory, mock_mysql):
        # Create a GR in bucket keys but don't hydrate (simulates missing data)
        mock_mysql._mock_golden["G-phantom"] = {
            "golden_record_id": "G-phantom",
            "canonical_name": "PHANTOM",
            "status": "ACTIVE",
            "bucket_keys": ["name:BOBS+TX"],
        }
        persona = persona_factory()
        result = mock_evaluator.find_candidates(persona)
        # Should not crash, phantom gets hydrated or skipped
        assert isinstance(result["candidates"], list)


# ══════════════════════════════════════════════════════════════
# TestCompareFields
# ══════════════════════════════════════════════════════════════

class TestCompareFields:
    def test_ein_disqualifies(self, mock_evaluator, persona_factory):
        orphan = persona_factory(ein="111111111")
        candidate = {
            "persona": {
                "identity": {"ein_clean": "222222222", "normalized_name": "TEST"},
                "location": {"state": "TX"},
            },
            "name_variants": [],
        }
        result = mock_evaluator.compare_fields(orphan, candidate)
        assert result.disqualified is True
        assert "EIN" in result.disqualification_reason

    def test_ontology_consulted_for_different_sectors(self, mock_evaluator, persona_factory):
        orphan = persona_factory(naics_code="238220", naics_sector="23")
        candidate = {
            "persona": {
                "identity": {"normalized_name": "OTHER"},
                "industry": {"naics_code": "423710", "naics_sector": "42"},
                "location": {"state": "TX"},
            },
            "name_variants": [],
        }
        result = mock_evaluator.compare_fields(orphan, candidate)
        # Should not crash; ontology fallback returns conservative result
        assert isinstance(result, ComparisonResult)
        assert result.disqualified is False


# ══════════════════════════════════════════════════════════════
# TestSemanticSimilarity
# ══════════════════════════════════════════════════════════════

class TestSemanticSimilarity:
    def test_returns_similarity_result(self, mock_evaluator, persona_factory):
        orphan = persona_factory()
        candidate = {
            "persona": {
                "identity": {"normalized_name": "BOBS PLUMBING"},
                "industry": {"naics_code": "238220"},
                "commodity": {"top_keywords": ["pvc"]},
                "location": {"state": "TX", "city_norm": "AUSTIN"},
            },
        }
        result = mock_evaluator.semantic_similarity(orphan, candidate)
        assert isinstance(result, SimilarityResult)
        assert result.composite_similarity >= 0.0

    def test_model_used_propagated(self, mock_evaluator, persona_factory):
        orphan = persona_factory()
        candidate = {
            "persona": {"identity": {"normalized_name": "TEST"}},
        }
        result = mock_evaluator.semantic_similarity(orphan, candidate)
        assert result.model_used == "mock"
