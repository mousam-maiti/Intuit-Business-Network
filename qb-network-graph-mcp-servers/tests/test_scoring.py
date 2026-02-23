"""Tests for utils/scoring.py — deterministic field comparison logic."""
import pytest
from models.persona import ClassifiedPersona, IdentityDimension, IndustryDimension, LocationDimension, CommodityDimension, BehavioralDimension
from models.resolution import DimensionConfidence, FieldMatchResult, DimensionResult
from utils.scoring import (
    jaro_winkler, jaccard_tokens, jaccard_keywords,
    match_ein, match_phone, match_email,
    score_identity, score_industry, score_location,
    score_commodity, score_behavioral, compute_composite,
)


# ── String similarity ───────────────────────────────────────

class TestJaroWinkler:
    def test_identical_strings(self):
        assert jaro_winkler("hello", "hello") == pytest.approx(1.0)

    def test_case_insensitive(self):
        assert jaro_winkler("Hello", "hello") == pytest.approx(1.0)

    def test_similar_strings(self):
        sim = jaro_winkler("BOBS PLUMBING", "BOB PLUMBING")
        assert 0.8 < sim < 1.0

    def test_different_strings(self):
        sim = jaro_winkler("ALPHA", "OMEGA")
        assert sim < 0.8

    def test_empty_first(self):
        assert jaro_winkler("", "hello") == 0.0

    def test_empty_second(self):
        assert jaro_winkler("hello", "") == 0.0

    def test_both_empty(self):
        assert jaro_winkler("", "") == 0.0

    def test_none_first(self):
        assert jaro_winkler(None, "hello") == 0.0

    def test_none_second(self):
        assert jaro_winkler("hello", None) == 0.0

    def test_single_char(self):
        sim = jaro_winkler("a", "a")
        assert sim == pytest.approx(1.0)


class TestJaccardTokens:
    def test_identical_sets(self):
        assert jaccard_tokens({"A", "B"}, {"A", "B"}) == pytest.approx(1.0)

    def test_no_overlap(self):
        assert jaccard_tokens({"A"}, {"B"}) == pytest.approx(0.0)

    def test_partial_overlap(self):
        assert jaccard_tokens({"A", "B", "C"}, {"A", "B", "D"}) == pytest.approx(0.5)

    def test_both_empty(self):
        assert jaccard_tokens(set(), set()) == 0.0

    def test_one_empty(self):
        assert jaccard_tokens({"A"}, set()) == 0.0

    def test_subset(self):
        assert jaccard_tokens({"A", "B"}, {"A", "B", "C"}) == pytest.approx(2 / 3)


class TestJaccardKeywords:
    def test_case_insensitive(self):
        assert jaccard_keywords(["PVC Pipe"], ["pvc pipe"]) == pytest.approx(1.0)

    def test_with_whitespace(self):
        assert jaccard_keywords([" pvc pipe "], ["pvc pipe"]) == pytest.approx(1.0)

    def test_empty_strings_filtered(self):
        assert jaccard_keywords(["pvc", ""], ["pvc"]) == pytest.approx(1.0)

    def test_both_empty_lists(self):
        assert jaccard_keywords([], []) == 0.0

    def test_one_empty_list(self):
        assert jaccard_keywords(["pvc"], []) == 0.0

    def test_partial_overlap(self):
        result = jaccard_keywords(["pvc", "copper"], ["pvc", "steel"])
        assert result == pytest.approx(1 / 3)


# ── EIN / Phone / Email matching ────────────────────────────

class TestMatchEin:
    def test_exact_match(self):
        assert match_ein("123456789", "123456789") == FieldMatchResult.EXACT

    def test_mismatch(self):
        assert match_ein("123456789", "987654321") == FieldMatchResult.MISMATCH

    def test_one_missing(self):
        assert match_ein("123456789", None) == FieldMatchResult.MISSING

    def test_both_missing(self):
        assert match_ein(None, None) == FieldMatchResult.MISSING

    def test_whitespace_handling(self):
        assert match_ein(" 123456789 ", "123456789") == FieldMatchResult.EXACT

    def test_empty_string(self):
        assert match_ein("", "123456789") == FieldMatchResult.MISSING


class TestMatchPhone:
    def test_exact_match(self):
        assert match_phone("5125551234", "5125551234") == FieldMatchResult.EXACT

    def test_partial_last_7(self):
        assert match_phone("5125551234", "5555551234") == FieldMatchResult.PARTIAL

    def test_mismatch(self):
        assert match_phone("5125551234", "5125559999") == FieldMatchResult.MISMATCH

    def test_one_missing(self):
        assert match_phone(None, "5125551234") == FieldMatchResult.MISSING

    def test_both_missing(self):
        assert match_phone(None, None) == FieldMatchResult.MISSING

    def test_short_phone(self):
        """Phones shorter than 7 digits can't partial match."""
        assert match_phone("1234", "5551234") == FieldMatchResult.MISMATCH

    def test_both_short(self):
        assert match_phone("123", "123") == FieldMatchResult.EXACT


class TestMatchEmail:
    def test_exact_match(self):
        assert match_email("bob@test.com", "bob@test.com") == FieldMatchResult.EXACT

    def test_case_insensitive(self):
        assert match_email("Bob@Test.COM", "bob@test.com") == FieldMatchResult.EXACT

    def test_domain_match(self):
        assert match_email("bob@test.com", "alice@test.com") == FieldMatchResult.DOMAIN_MATCH

    def test_mismatch(self):
        assert match_email("bob@test.com", "bob@other.com") == FieldMatchResult.MISMATCH

    def test_one_missing(self):
        assert match_email(None, "bob@test.com") == FieldMatchResult.MISSING

    def test_both_missing(self):
        assert match_email(None, None) == FieldMatchResult.MISSING

    def test_no_at_sign(self):
        """Emails without @ shouldn't domain match."""
        assert match_email("bob", "alice") == FieldMatchResult.MISMATCH

    def test_whitespace(self):
        assert match_email(" bob@test.com ", "bob@test.com") == FieldMatchResult.EXACT


# ── Identity scoring ────────────────────────────────────────

class TestScoreIdentity:
    def _persona(self, **overrides):
        defaults = {
            "normalized_name": "Bob's Plumbing LLC",
            "name_first_token": "BOBS",
            "name_tokens": ["BOBS", "PLUMBING", "LLC"],
            "ein_clean": "743218976",
            "phone_digits": "5124551234",
            "email": "bob@bobsplumbing.com",
        }
        defaults.update(overrides)
        return ClassifiedPersona(identity=IdentityDimension(**defaults))

    def test_identical_high_score(self):
        p = self._persona()
        result = score_identity(p, p, ["Bob's Plumbing LLC"])
        assert result.score == 1.0
        assert result.confidence == DimensionConfidence.HIGH

    def test_ein_exact_signals(self):
        o = self._persona()
        c = self._persona(normalized_name="Different Name", name_tokens=["DIFFERENT", "NAME"])
        result = score_identity(o, c, [])
        assert result.score >= 0.9  # EIN exact appends 1.0

    def test_name_in_variants(self):
        o = self._persona(ein_clean=None, phone_digits=None, email=None)
        c = self._persona(
            normalized_name="Different Name",
            name_tokens=["DIFFERENT", "NAME"],
            ein_clean=None, phone_digits=None, email=None,
        )
        result = score_identity(o, c, ["Bob's Plumbing LLC"])
        assert result.score == 1.0

    def test_phone_partial_signal(self):
        o = self._persona(ein_clean=None, email=None, normalized_name="A", name_tokens=["A"])
        c = self._persona(
            ein_clean=None, email=None,
            normalized_name="B", name_tokens=["B"],
            phone_digits="9994551234",  # last 7 match
        )
        result = score_identity(o, c, [])
        assert result.score >= 0.6

    def test_email_domain_match(self):
        o = self._persona(ein_clean=None, phone_digits=None, normalized_name="A", name_tokens=["A"])
        c = self._persona(
            ein_clean=None, phone_digits=None,
            normalized_name="B", name_tokens=["B"],
            email="alice@bobsplumbing.com",
        )
        result = score_identity(o, c, [])
        assert result.score >= 0.5

    def test_no_data_insufficient(self):
        p = ClassifiedPersona(identity=IdentityDimension())
        result = score_identity(p, p, [])
        assert result.confidence == DimensionConfidence.INSUFFICIENT

    def test_confidence_medium(self):
        """2 available fields → MEDIUM confidence."""
        p = self._persona(phone_digits=None, email=None)
        result = score_identity(p, p, [])
        assert result.confidence == DimensionConfidence.MEDIUM

    def test_confidence_low(self):
        """1 available field → LOW confidence."""
        p = self._persona(ein_clean=None, phone_digits=None, email=None)
        result = score_identity(p, p, [])
        assert result.confidence == DimensionConfidence.LOW

    def test_details_populated(self):
        p = self._persona()
        result = score_identity(p, p, ["Bob's Plumbing LLC"])
        assert "ein_match" in result.details
        assert "phone_match" in result.details
        assert "email_match" in result.details
        assert "name_similarity" in result.details
        assert "name_token_overlap" in result.details
        assert "name_in_variants" in result.details


# ── Industry scoring ────────────────────────────────────────

class TestScoreIndustry:
    def _persona(self, naics_code=None):
        return ClassifiedPersona(
            industry=IndustryDimension(naics_code=naics_code)
        )

    def test_both_missing(self):
        result = score_industry(self._persona(), self._persona())
        assert result.score == 0.0
        assert result.confidence == DimensionConfidence.INSUFFICIENT

    def test_one_missing(self):
        result = score_industry(self._persona("238220"), self._persona())
        assert result.score == 0.0
        assert result.confidence == DimensionConfidence.INSUFFICIENT

    def test_exact_match(self):
        result = score_industry(self._persona("238220"), self._persona("238220"))
        assert result.score == 1.0
        assert result.confidence == DimensionConfidence.HIGH

    def test_subsector_match(self):
        result = score_industry(self._persona("238220"), self._persona("238210"))
        assert result.score == 0.8
        assert result.confidence == DimensionConfidence.HIGH

    def test_sector_match(self):
        result = score_industry(self._persona("238220"), self._persona("236220"))
        assert result.score == 0.5
        assert result.confidence == DimensionConfidence.MEDIUM

    def test_different_sectors_with_ontology(self):
        result = score_industry(self._persona("238220"), self._persona("424710"), ontology_score=0.4)
        assert result.score == 0.4
        assert result.confidence == DimensionConfidence.MEDIUM

    def test_different_sectors_low_ontology(self):
        result = score_industry(self._persona("238220"), self._persona("424710"), ontology_score=0.1)
        assert result.score == 0.1
        assert result.confidence == DimensionConfidence.LOW

    def test_different_sectors_no_ontology(self):
        result = score_industry(self._persona("238220"), self._persona("424710"))
        assert result.score == 0.0
        assert result.confidence == DimensionConfidence.LOW

    def test_short_codes(self):
        """Codes shorter than 3 can't subsector match."""
        result = score_industry(self._persona("23"), self._persona("24"))
        assert result.score == 0.0  # different sectors, no ontology


# ── Location scoring ────────────────────────────────────────

class TestScoreLocation:
    def _persona(self, state="TX", city_norm=None, zip3=None, zip5=None):
        return ClassifiedPersona(
            location=LocationDimension(state=state, city_norm=city_norm, zip3=zip3, zip5=zip5)
        )

    def test_state_missing(self):
        result = score_location(self._persona(state=""), self._persona(state="TX"))
        assert result.score == 0.0
        assert result.confidence == DimensionConfidence.INSUFFICIENT

    def test_both_state_missing(self):
        result = score_location(self._persona(state=""), self._persona(state=""))
        assert result.score == 0.0
        assert result.confidence == DimensionConfidence.INSUFFICIENT

    def test_state_mismatch(self):
        result = score_location(self._persona(state="TX"), self._persona(state="CA"))
        assert result.score == 0.0
        assert result.details["state_match"] is False

    def test_state_case_insensitive(self):
        result = score_location(self._persona(state="tx"), self._persona(state="TX"))
        assert result.score > 0.0
        assert result.details.get("state_match") is True

    def test_zip5_match(self):
        result = score_location(
            self._persona(state="TX", zip5="78704"),
            self._persona(state="TX", zip5="78704"),
        )
        assert result.score == 1.0
        assert result.confidence == DimensionConfidence.HIGH

    def test_zip3_match(self):
        result = score_location(
            self._persona(state="TX", zip3="787"),
            self._persona(state="TX", zip3="787"),
        )
        assert result.score == 0.8

    def test_city_match(self):
        result = score_location(
            self._persona(state="TX", city_norm="AUSTIN"),
            self._persona(state="TX", city_norm="AUSTIN"),
        )
        assert result.score == 0.7

    def test_city_case_insensitive(self):
        result = score_location(
            self._persona(state="TX", city_norm="austin"),
            self._persona(state="TX", city_norm="AUSTIN"),
        )
        assert result.score == 0.7

    def test_state_only(self):
        result = score_location(self._persona(state="TX"), self._persona(state="TX"))
        assert result.score == 0.3


# ── Commodity scoring ───────────────────────────────────────

class TestScoreCommodity:
    def _persona(self, keywords=None):
        return ClassifiedPersona(
            commodity=CommodityDimension(top_keywords=keywords or [])
        )

    def test_both_empty(self):
        result = score_commodity(self._persona(), self._persona())
        assert result.score == 0.0
        assert result.confidence == DimensionConfidence.INSUFFICIENT

    def test_one_empty(self):
        result = score_commodity(self._persona(["pvc"]), self._persona())
        assert result.score == 0.0
        assert result.confidence == DimensionConfidence.INSUFFICIENT

    def test_identical_keywords(self):
        result = score_commodity(
            self._persona(["pvc pipe", "copper"]),
            self._persona(["pvc pipe", "copper"]),
        )
        assert result.score == 1.0
        assert result.confidence == DimensionConfidence.HIGH

    def test_partial_overlap(self):
        result = score_commodity(
            self._persona(["pvc", "copper", "steel"]),
            self._persona(["pvc", "copper", "wood"]),
        )
        assert 0.3 < result.score < 1.0

    def test_no_overlap(self):
        result = score_commodity(
            self._persona(["pvc"]),
            self._persona(["wood"]),
        )
        assert result.score == 0.0
        assert result.confidence == DimensionConfidence.LOW

    def test_overlapping_keywords_in_details(self):
        result = score_commodity(
            self._persona(["pvc", "copper"]),
            self._persona(["PVC", "steel"]),
        )
        assert "pvc" in result.details["overlapping_keywords"]


# ── Behavioral scoring ──────────────────────────────────────

class TestScoreBehavioral:
    def _persona(self, bracket=None, avg_txn=None, count=None):
        return ClassifiedPersona(
            behavioral=BehavioralDimension(
                volume_bracket=bracket,
                avg_transaction=avg_txn,
                transaction_count=count,
            )
        )

    def test_both_missing(self):
        result = score_behavioral(self._persona(), self._persona())
        assert result.score == 0.0
        assert result.confidence == DimensionConfidence.INSUFFICIENT

    def test_one_missing(self):
        result = score_behavioral(self._persona("MEDIUM"), self._persona())
        assert result.score == 0.0
        assert result.confidence == DimensionConfidence.INSUFFICIENT

    def test_bracket_match(self):
        result = score_behavioral(self._persona("MEDIUM"), self._persona("MEDIUM"))
        assert result.score == 0.7
        assert result.confidence == DimensionConfidence.MEDIUM

    def test_bracket_mismatch(self):
        result = score_behavioral(self._persona("HIGH"), self._persona("LOW"))
        assert result.score == 0.3
        assert result.confidence == DimensionConfidence.LOW

    def test_volume_ratio_within_10x(self):
        result = score_behavioral(
            self._persona("MEDIUM", avg_txn=200.0),
            self._persona("MEDIUM", avg_txn=250.0),
        )
        assert result.score >= 0.6

    def test_volume_ratio_outside_10x(self):
        result = score_behavioral(
            self._persona("LOW", avg_txn=10.0),
            self._persona("LOW", avg_txn=500.0),  # ratio = 0.02
        )
        assert result.score <= 0.2

    def test_zero_avg_transaction(self):
        """Division by zero should be avoided."""
        result = score_behavioral(
            self._persona("MEDIUM", avg_txn=100.0),
            self._persona("MEDIUM", avg_txn=0),
        )
        assert result.score == 0.7  # bracket match, but no volume check

    def test_details_populated(self):
        result = score_behavioral(
            self._persona("HIGH", avg_txn=500.0),
            self._persona("LOW", avg_txn=50.0),
        )
        assert "volume_bracket_match" in result.details
        assert "orphan_bracket" in result.details
        assert "candidate_bracket" in result.details


# ── Composite scoring ───────────────────────────────────────

class TestComputeComposite:
    def test_all_available(self):
        dims = {
            "identity": DimensionResult(score=0.9, confidence=DimensionConfidence.HIGH),
            "industry": DimensionResult(score=0.8, confidence=DimensionConfidence.HIGH),
            "location": DimensionResult(score=1.0, confidence=DimensionConfidence.HIGH),
            "commodity": DimensionResult(score=0.5, confidence=DimensionConfidence.MEDIUM),
            "behavioral": DimensionResult(score=0.7, confidence=DimensionConfidence.MEDIUM),
        }
        weights = {"identity": 0.35, "industry": 0.25, "location": 0.15, "commodity": 0.15, "behavioral": 0.10}
        composite, used_weights, sparsity = compute_composite(dims, weights)

        assert not sparsity
        expected = 0.35 * 0.9 + 0.25 * 0.8 + 0.15 * 1.0 + 0.15 * 0.5 + 0.10 * 0.7
        assert composite == pytest.approx(expected, abs=0.001)

    def test_weight_redistribution(self):
        dims = {
            "identity": DimensionResult(score=0.9, confidence=DimensionConfidence.HIGH),
            "industry": DimensionResult(score=0.8, confidence=DimensionConfidence.HIGH),
            "location": DimensionResult(score=0.0, confidence=DimensionConfidence.INSUFFICIENT),
            "commodity": DimensionResult(score=0.0, confidence=DimensionConfidence.INSUFFICIENT),
            "behavioral": DimensionResult(score=0.0, confidence=DimensionConfidence.INSUFFICIENT),
        }
        weights = {"identity": 0.35, "industry": 0.25, "location": 0.15, "commodity": 0.15, "behavioral": 0.10}
        composite, used_weights, sparsity = compute_composite(dims, weights)

        assert sparsity is True
        # Only identity and industry available, weights redistributed proportionally
        total_avail = 0.35 + 0.25
        assert used_weights["identity"] == pytest.approx(0.35 + 0.40 * (0.35 / total_avail), abs=0.001)
        assert used_weights["industry"] == pytest.approx(0.25 + 0.40 * (0.25 / total_avail), abs=0.001)

    def test_all_insufficient(self):
        dims = {
            "identity": DimensionResult(score=0.0, confidence=DimensionConfidence.INSUFFICIENT),
            "industry": DimensionResult(score=0.0, confidence=DimensionConfidence.INSUFFICIENT),
        }
        weights = {"identity": 0.5, "industry": 0.5}
        composite, used_weights, sparsity = compute_composite(dims, weights)

        assert composite == 0.0
        assert sparsity is False  # no available dims, returns base weights

    def test_missing_dimension(self):
        """Dimensions not in the dict should be treated as insufficient."""
        dims = {"identity": DimensionResult(score=0.9, confidence=DimensionConfidence.HIGH)}
        weights = {"identity": 0.5, "industry": 0.5}
        composite, used_weights, sparsity = compute_composite(dims, weights)

        assert sparsity is True
        assert composite == pytest.approx(0.9, abs=0.001)  # all weight goes to identity

    def test_weights_rounded(self):
        dims = {
            "identity": DimensionResult(score=0.5, confidence=DimensionConfidence.HIGH),
            "industry": DimensionResult(score=0.5, confidence=DimensionConfidence.HIGH),
        }
        weights = {"identity": 0.333, "industry": 0.333, "location": 0.334}
        _, used_weights, _ = compute_composite(dims, weights)
        for v in used_weights.values():
            assert len(str(v).split(".")[-1]) <= 4
