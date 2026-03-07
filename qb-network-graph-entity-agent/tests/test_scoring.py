"""
Tests for utils/scoring.py — edge cases and behavioral dimension (zero existing tests).
"""
import pytest
from models.persona import ClassifiedPersona, IdentityDimension, IndustryDimension, LocationDimension, CommodityDimension, BehavioralDimension
from models.resolution import DimensionResult, DimensionConfidence
from utils.scoring import (
    jaro_winkler, jaccard_tokens, jaccard_keywords,
    match_ein, match_phone, match_email,
    score_identity, score_industry, score_location,
    score_commodity, score_behavioral, compute_composite,
)
from models.resolution import FieldMatchResult


# ══════════════════════════════════════════════════════════════
# TestJaroWinklerEdgeCases
# ══════════════════════════════════════════════════════════════

class TestJaroWinklerEdgeCases:
    def test_case_insensitive(self):
        assert jaro_winkler("Hello", "hello") == jaro_winkler("HELLO", "hello")

    def test_both_empty(self):
        assert jaro_winkler("", "") == 0.0


# ══════════════════════════════════════════════════════════════
# TestJaccardEdgeCases
# ══════════════════════════════════════════════════════════════

class TestJaccardEdgeCases:
    def test_both_empty(self):
        assert jaccard_tokens(set(), set()) == 0.0

    def test_one_empty(self):
        assert jaccard_tokens({"a", "b"}, set()) == 0.0

    def test_superset(self):
        assert jaccard_tokens({"a", "b"}, {"a", "b", "c"}) == pytest.approx(2 / 3)


# ══════════════════════════════════════════════════════════════
# TestJaccardKeywords
# ══════════════════════════════════════════════════════════════

class TestJaccardKeywords:
    def test_case_normalization(self):
        assert jaccard_keywords(["PVC Pipe"], ["pvc pipe"]) == 1.0

    def test_whitespace_stripping(self):
        assert jaccard_keywords(["  pvc  "], ["pvc"]) == 1.0

    def test_empty_strings_filtered(self):
        assert jaccard_keywords(["pvc", ""], ["pvc"]) == 1.0

    def test_both_empty_lists(self):
        assert jaccard_keywords([], []) == 0.0


# ══════════════════════════════════════════════════════════════
# TestMatchEinEdgeCases
# ══════════════════════════════════════════════════════════════

class TestMatchEinEdgeCases:
    def test_whitespace_stripped(self):
        assert match_ein(" 123456789 ", "123456789") == FieldMatchResult.EXACT

    def test_both_none(self):
        assert match_ein(None, None) == FieldMatchResult.MISSING

    def test_empty_string(self):
        assert match_ein("", "123") == FieldMatchResult.MISSING


# ══════════════════════════════════════════════════════════════
# TestMatchPhoneEdgeCases
# ══════════════════════════════════════════════════════════════

class TestMatchPhoneEdgeCases:
    def test_both_none(self):
        assert match_phone(None, None) == FieldMatchResult.MISSING

    def test_mismatch(self):
        assert match_phone("5125551234", "5125559999") == FieldMatchResult.MISMATCH

    def test_partial_last_7_only(self):
        assert match_phone("15125551234", "5125551234") == FieldMatchResult.PARTIAL

    def test_short_numbers(self):
        assert match_phone("123", "456") == FieldMatchResult.MISMATCH


# ══════════════════════════════════════════════════════════════
# TestMatchEmailEdgeCases
# ══════════════════════════════════════════════════════════════

class TestMatchEmailEdgeCases:
    def test_both_none(self):
        assert match_email(None, None) == FieldMatchResult.MISSING

    def test_different_domain_mismatch(self):
        assert match_email("bob@aol.com", "bob@gmail.com") == FieldMatchResult.MISMATCH

    def test_case_insensitive(self):
        assert match_email("Bob@Test.Com", "bob@test.com") == FieldMatchResult.EXACT

    def test_no_at_sign(self):
        assert match_email("notanemail", "another") == FieldMatchResult.MISMATCH


# ══════════════════════════════════════════════════════════════
# TestScoreIdentityEdgeCases
# ══════════════════════════════════════════════════════════════

class TestScoreIdentityEdgeCases:
    def _make(self, **kwargs):
        return ClassifiedPersona(identity=IdentityDimension(**kwargs))

    def test_name_in_variants_score_1(self):
        orphan = self._make(normalized_name="BOBS PLUMBING")
        cand = self._make(normalized_name="BP LLC")
        result = score_identity(orphan, cand, ["BOBS PLUMBING", "BP LLC"])
        assert result.score == 1.0

    def test_phone_partial_0_6(self):
        orphan = self._make(normalized_name="TEST", phone_digits="15125551234")
        cand = self._make(normalized_name="TEST", phone_digits="5125551234")
        result = score_identity(orphan, cand, [])
        assert result.score >= 0.6

    def test_email_domain_0_5(self):
        orphan = self._make(normalized_name="TEST", email="bob@example.com")
        cand = self._make(normalized_name="TEST", email="alice@example.com")
        result = score_identity(orphan, cand, [])
        assert result.score >= 0.5

    def test_confidence_insufficient_no_fields(self):
        orphan = self._make()
        cand = self._make()
        result = score_identity(orphan, cand, [])
        assert result.confidence == DimensionConfidence.INSUFFICIENT


# ══════════════════════════════════════════════════════════════
# TestScoreIndustryEdgeCases
# ══════════════════════════════════════════════════════════════

class TestScoreIndustryEdgeCases:
    def _make(self, naics=None):
        return ClassifiedPersona(industry=IndustryDimension(naics_code=naics))

    def test_both_missing(self):
        result = score_industry(self._make(), self._make())
        assert result.confidence == DimensionConfidence.INSUFFICIENT

    def test_one_missing(self):
        result = score_industry(self._make("238220"), self._make())
        assert result.confidence == DimensionConfidence.INSUFFICIENT

    def test_ontology_score_affects_confidence(self):
        result = score_industry(self._make("238220"), self._make("423710"), ontology_score=0.4)
        assert result.score == 0.4
        assert result.confidence == DimensionConfidence.MEDIUM


# ══════════════════════════════════════════════════════════════
# TestScoreLocationEdgeCases
# ══════════════════════════════════════════════════════════════

class TestScoreLocationEdgeCases:
    def _make(self, state="", city=None, zip3=None, zip5=None):
        return ClassifiedPersona(
            location=LocationDimension(state=state, city_norm=city, zip3=zip3, zip5=zip5)
        )

    def test_state_missing(self):
        result = score_location(self._make(), self._make("TX"))
        assert result.confidence == DimensionConfidence.INSUFFICIENT

    def test_zip3_match(self):
        result = score_location(self._make("TX", zip3="787"), self._make("TX", zip3="787"))
        assert result.score == 0.8

    def test_case_insensitive_city(self):
        result = score_location(self._make("TX", city="austin"), self._make("TX", city="AUSTIN"))
        assert result.score == 0.7


# ══════════════════════════════════════════════════════════════
# TestScoreCommodityEdgeCases
# ══════════════════════════════════════════════════════════════

class TestScoreCommodityEdgeCases:
    def _make(self, keywords=None):
        return ClassifiedPersona(
            commodity=CommodityDimension(top_keywords=keywords or [])
        )

    def test_both_empty(self):
        result = score_commodity(self._make(), self._make())
        assert result.confidence == DimensionConfidence.INSUFFICIENT

    def test_one_empty(self):
        result = score_commodity(self._make(["pvc"]), self._make())
        assert result.confidence == DimensionConfidence.INSUFFICIENT

    def test_no_overlap(self):
        result = score_commodity(self._make(["pvc"]), self._make(["lumber"]))
        assert result.score == 0.0


# ══════════════════════════════════════════════════════════════
# TestScoreBehavioral — NEW (zero existing tests)
# ══════════════════════════════════════════════════════════════

class TestScoreBehavioral:
    def _make(self, bracket=None, avg_txn=None, txn_count=None):
        return ClassifiedPersona(
            behavioral=BehavioralDimension(
                volume_bracket=bracket,
                avg_transaction=avg_txn,
                transaction_count=txn_count,
            )
        )

    def test_bracket_missing(self):
        result = score_behavioral(self._make(), self._make())
        assert result.confidence == DimensionConfidence.INSUFFICIENT
        assert result.details.get("reason") == "bracket_missing"

    def test_bracket_match(self):
        result = score_behavioral(self._make("MEDIUM"), self._make("MEDIUM"))
        assert result.score == 0.7
        assert result.confidence == DimensionConfidence.MEDIUM

    def test_bracket_mismatch(self):
        result = score_behavioral(self._make("HIGH"), self._make("LOW"))
        assert result.score == 0.3
        assert result.confidence == DimensionConfidence.LOW

    def test_volume_ratio_within_10x(self):
        result = score_behavioral(
            self._make("HIGH", avg_txn=5000.0),
            self._make("HIGH", avg_txn=1000.0),
        )
        assert result.score >= 0.6

    def test_volume_ratio_outside_10x(self):
        result = score_behavioral(
            self._make("HIGH", avg_txn=50000.0),
            self._make("HIGH", avg_txn=1.0),
        )
        assert result.score <= 0.2


# ══════════════════════════════════════════════════════════════
# TestCompositeEdgeCases
# ══════════════════════════════════════════════════════════════

class TestCompositeEdgeCases:
    def test_single_dimension_available(self):
        dims = {
            "identity": DimensionResult(score=0.9, confidence=DimensionConfidence.HIGH),
            "industry": DimensionResult(score=0.0, confidence=DimensionConfidence.INSUFFICIENT),
            "location": DimensionResult(score=0.0, confidence=DimensionConfidence.INSUFFICIENT),
            "commodity": DimensionResult(score=0.0, confidence=DimensionConfidence.INSUFFICIENT),
            "behavioral": DimensionResult(score=0.0, confidence=DimensionConfidence.INSUFFICIENT),
        }
        weights = {"identity": 0.35, "industry": 0.25, "location": 0.15, "commodity": 0.15, "behavioral": 0.10}
        score, used, adjusted = compute_composite(dims, weights)
        # All weight redistributed to identity: 0.9 * 1.0 = 0.9
        assert score == pytest.approx(0.9, abs=0.01)
        assert adjusted is True

    def test_all_zero_scores(self):
        dims = {
            "identity": DimensionResult(score=0.0, confidence=DimensionConfidence.HIGH),
            "industry": DimensionResult(score=0.0, confidence=DimensionConfidence.HIGH),
            "location": DimensionResult(score=0.0, confidence=DimensionConfidence.HIGH),
            "commodity": DimensionResult(score=0.0, confidence=DimensionConfidence.HIGH),
            "behavioral": DimensionResult(score=0.0, confidence=DimensionConfidence.HIGH),
        }
        weights = {"identity": 0.35, "industry": 0.25, "location": 0.15, "commodity": 0.15, "behavioral": 0.10}
        score, _, adjusted = compute_composite(dims, weights)
        assert score == 0.0
        assert adjusted is False

    def test_weight_redistribution_math(self):
        # identity: 0.9 (HIGH), industry: 0.8 (HIGH), rest INSUFFICIENT
        dims = {
            "identity": DimensionResult(score=0.9, confidence=DimensionConfidence.HIGH),
            "industry": DimensionResult(score=0.8, confidence=DimensionConfidence.HIGH),
            "location": DimensionResult(score=0.0, confidence=DimensionConfidence.INSUFFICIENT),
            "commodity": DimensionResult(score=0.0, confidence=DimensionConfidence.INSUFFICIENT),
            "behavioral": DimensionResult(score=0.0, confidence=DimensionConfidence.INSUFFICIENT),
        }
        weights = {"identity": 0.35, "industry": 0.25, "location": 0.15, "commodity": 0.15, "behavioral": 0.10}
        score, used, adjusted = compute_composite(dims, weights)
        # Redistribute 0.40 (loc+comm+behav) to identity+industry proportionally
        # identity gets 0.35 + 0.40*(0.35/0.60) = 0.35 + 0.2333 = 0.5833
        # industry gets 0.25 + 0.40*(0.25/0.60) = 0.25 + 0.1667 = 0.4167
        # Score = 0.9*0.5833 + 0.8*0.4167 = 0.5250 + 0.3333 = 0.8583
        assert score == pytest.approx(0.8583, abs=0.01)
        assert adjusted is True
