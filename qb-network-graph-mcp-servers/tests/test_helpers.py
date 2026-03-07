"""Tests for helper functions in tools/ modules."""
import pytest
from models.persona import ClassifiedPersona, IdentityDimension, IndustryDimension, LocationDimension, CommodityDimension, GoldenRecord

# ── candidate_tools helpers ──────────────────────────────────

from tools.candidate_tools import _parse_list, _parse_persona, _to_classified_persona as ct_to_cp, _persona_to_texts

class TestParseList:
    def test_string_json_list(self):
        assert _parse_list('["a", "b"]') == ["a", "b"]

    def test_string_non_json(self):
        assert _parse_list("hello") == ["hello"]

    def test_empty_string(self):
        assert _parse_list("") == []

    def test_actual_list(self):
        assert _parse_list(["a", "b"]) == ["a", "b"]

    def test_none(self):
        assert _parse_list(None) == []

    def test_dict(self):
        assert _parse_list({"a": 1}) == []

    def test_int(self):
        assert _parse_list(42) == []


class TestParsePersona:
    def test_json_string(self):
        result = _parse_persona('{"identity": {"normalized_name": "Test"}}')
        assert result["identity"]["normalized_name"] == "Test"

    def test_invalid_json(self):
        assert _parse_persona("not-json") == {}

    def test_empty_string(self):
        assert _parse_persona("") == {}

    def test_dict(self):
        d = {"identity": {"normalized_name": "Test"}}
        assert _parse_persona(d) == d

    def test_none(self):
        assert _parse_persona(None) == {}

    def test_list_not_dict(self):
        assert _parse_persona([1, 2]) == {}


class TestToClassifiedPersona:
    def test_already_classified_persona(self):
        p = ClassifiedPersona()
        result = ct_to_cp(p)
        assert result is p  # same object

    def test_valid_dict(self):
        d = {"identity": {"normalized_name": "Test"}, "location": {"state": "TX"}}
        result = ct_to_cp(d)
        assert result.identity.normalized_name == "Test"
        assert result.location.state == "TX"

    def test_invalid_dict(self):
        """Invalid data should return empty ClassifiedPersona."""
        result = ct_to_cp("not_a_dict")
        assert isinstance(result, ClassifiedPersona)
        assert result.identity.normalized_name == ""

    def test_empty_dict(self):
        result = ct_to_cp({})
        assert isinstance(result, ClassifiedPersona)


class TestPersonaToTexts:
    def test_full_persona(self):
        p = ClassifiedPersona(
            identity=IdentityDimension(
                normalized_name="Bob's Plumbing",
                legal_suffix="LLC",
            ),
            industry=IndustryDimension(
                naics_code="238220",
                commodity_keywords=["pvc pipe"],
            ),
            commodity=CommodityDimension(top_keywords=["pvc pipe", "copper"]),
            location=LocationDimension(state="TX", city_norm="AUSTIN", zip5="78704"),
        )
        texts = _persona_to_texts(p)
        assert "Bob's Plumbing" in texts["name"]
        assert "LLC" in texts["name"]
        assert "NAICS 238220" in texts["industry"]
        assert "pvc pipe" in texts["commodities"]
        assert "AUSTIN" in texts["location"]
        assert "TX" in texts["location"]

    def test_minimal_persona(self):
        p = ClassifiedPersona()
        texts = _persona_to_texts(p)
        assert texts["name"] == ""
        assert texts["industry"] == ""
        assert texts["commodities"] == ""
        assert texts["location"] == ""

    def test_no_legal_suffix(self):
        p = ClassifiedPersona(
            identity=IdentityDimension(normalized_name="Test Corp"),
        )
        texts = _persona_to_texts(p)
        assert texts["name"] == "Test Corp"


# ── entity_writer_tools helpers ──────────────────────────────

from tools.entity_writer_tools import (
    _to_classified_persona as ew_to_cp,
    _apply_survivorship, _resolve_canonical_name,
)


class TestApplySurvivorship:
    def _gr(self, **identity_kw):
        persona = ClassifiedPersona(
            identity=IdentityDimension(**identity_kw),
            location=LocationDimension(state="TX"),
            commodity=CommodityDimension(top_keywords=["existing"]),
        )
        return GoldenRecord(
            golden_record_id="G-001",
            canonical_name="Test",
            persona=persona,
        )

    def test_fills_missing_ein(self):
        gr = self._gr(normalized_name="Test")
        orphan = ClassifiedPersona(
            identity=IdentityDimension(ein_clean="123456789"),
        )
        _apply_survivorship(gr, orphan)
        assert gr.persona.identity.ein_clean == "123456789"

    def test_does_not_overwrite_existing_ein(self):
        gr = self._gr(normalized_name="Test", ein_clean="999999999")
        orphan = ClassifiedPersona(
            identity=IdentityDimension(ein_clean="123456789"),
        )
        _apply_survivorship(gr, orphan)
        assert gr.persona.identity.ein_clean == "999999999"

    def test_fills_missing_phone(self):
        gr = self._gr(normalized_name="Test")
        orphan = ClassifiedPersona(
            identity=IdentityDimension(phone_digits="5125551234"),
        )
        _apply_survivorship(gr, orphan)
        assert gr.persona.identity.phone_digits == "5125551234"

    def test_fills_missing_email(self):
        gr = self._gr(normalized_name="Test")
        orphan = ClassifiedPersona(
            identity=IdentityDimension(email="bob@test.com", email_domain="test.com"),
        )
        _apply_survivorship(gr, orphan)
        assert gr.persona.identity.email == "bob@test.com"
        assert gr.persona.identity.email_domain == "test.com"

    def test_naics_more_specific_wins(self):
        gr = self._gr(normalized_name="Test")
        gr.persona.industry.naics_code = "23"
        orphan = ClassifiedPersona(
            industry=IndustryDimension(naics_code="238220", naics_sector="23", naics_subsector="238"),
        )
        _apply_survivorship(gr, orphan)
        assert gr.persona.industry.naics_code == "238220"  # more specific

    def test_naics_less_specific_kept(self):
        gr = self._gr(normalized_name="Test")
        gr.persona.industry.naics_code = "238220"
        orphan = ClassifiedPersona(
            industry=IndustryDimension(naics_code="23"),
        )
        _apply_survivorship(gr, orphan)
        assert gr.persona.industry.naics_code == "238220"  # existing more specific

    def test_fills_missing_city(self):
        gr = self._gr(normalized_name="Test")
        orphan = ClassifiedPersona(
            location=LocationDimension(city_norm="AUSTIN"),
        )
        _apply_survivorship(gr, orphan)
        assert gr.persona.location.city_norm == "AUSTIN"

    def test_merges_commodity_keywords(self):
        gr = self._gr(normalized_name="Test")
        orphan = ClassifiedPersona(
            commodity=CommodityDimension(top_keywords=["new_keyword", "existing"]),
        )
        _apply_survivorship(gr, orphan)
        kw_lower = [k.lower() for k in gr.persona.commodity.top_keywords]
        assert "new_keyword" in kw_lower
        assert kw_lower.count("existing") == 1  # no duplicates


class TestResolveCanonicalName:
    def test_normalized_name(self):
        p = ClassifiedPersona(identity=IdentityDimension(normalized_name="Test Corp"))
        assert _resolve_canonical_name(p) == "Test Corp"

    def test_fallback_to_first_token(self):
        p = ClassifiedPersona(identity=IdentityDimension(name_first_token="BOBS"))
        assert _resolve_canonical_name(p) == "BOBS"

    def test_empty_returns_empty(self):
        p = ClassifiedPersona()
        assert _resolve_canonical_name(p) == ""


# ── knowledge_graph_tools helpers ────────────────────────────

from tools.knowledge_graph_tools import (
    _query_ontology_internal, _query_commodity_relation,
    _query_geo_containment, _build_industry_explanation,
)
from clients.neo4j_client import Neo4jClient


class TestQueryCommodityRelation:
    def test_identical_codes(self):
        result = _query_commodity_relation("238220", "238220")
        assert result["related"] is True
        assert result["relationship_type"] == "SAME"
        assert result["semantic_distance"] == 0.0

    def test_similar_codes(self):
        """238220 vs 238210: shared prefix is 4/6 = distance 0.333 — not SIBLING (< 0.3) but still related (< 0.5)."""
        result = _query_commodity_relation("238220", "238210")
        assert result["related"] is True
        assert result["semantic_distance"] == pytest.approx(0.333, abs=0.01)

    def test_very_similar_codes(self):
        """238221 vs 238222: shared prefix is 5/6 = distance 0.167 — SIBLING."""
        result = _query_commodity_relation("238221", "238222")
        assert result["related"] is True
        assert result["relationship_type"] == "SIBLING"

    def test_different_codes(self):
        result = _query_commodity_relation("238220", "511210")
        assert result["related"] is False


class TestQueryGeoContainment:
    def test_same_geo(self):
        result = _query_geo_containment("TX", "TX")
        assert result["related"] is True
        assert result["relationship_type"] == "SAME"

    def test_case_insensitive(self):
        result = _query_geo_containment("tx", "TX")
        assert result["related"] is True

    def test_different_geo(self):
        result = _query_geo_containment("TX", "CA")
        assert result["related"] is False


class TestBuildIndustryExplanation:
    def test_same_type(self):
        result = _build_industry_explanation("238220", "238220", [], [], None, [], "SAME")
        assert "Same NAICS" in result

    def test_sibling_type(self):
        result = _build_industry_explanation("238220", "238210", [], [], "238", [], "SIBLING")
        assert "subsector" in result.lower()

    def test_cross_taxonomy_type(self):
        links = [{"label": "Plumbing Supplies", "code": "33261"}]
        result = _build_industry_explanation("238220", "424710", [], [], None, links, "CROSS_TAXONOMY_LINK")
        assert "Plumbing Supplies" in result

    def test_unrelated_type(self):
        result = _build_industry_explanation("238220", "511210", [], [], None, [], "UNRELATED")
        assert "unrelated" in result.lower()

    def test_ancestor_type(self):
        result = _build_industry_explanation("238220", "236220", [], [], "23", [], "ANCESTOR")
        # ANCESTOR case falls through to default
        assert "unrelated" in result.lower() or "NAICS" in result


# ── Neo4j NAICS taxonomy (pure Python, replaces _fallback_ontology) ───

class TestNaicsHierarchy:
    def test_6_digit_code(self):
        path = Neo4jClient.query_naics_hierarchy("238220")
        assert path == ["238220", "23822", "2382", "238", "23"]

    def test_2_digit_code(self):
        path = Neo4jClient.query_naics_hierarchy("23")
        assert path == ["23"]

    def test_empty_code(self):
        path = Neo4jClient.query_naics_hierarchy("")
        assert path == []


class TestLowestCommonAncestor:
    def test_same_subsector(self):
        lca = Neo4jClient.query_lowest_common_ancestor("238220", "238210")
        assert lca == "2382"

    def test_same_sector(self):
        lca = Neo4jClient.query_lowest_common_ancestor("238220", "236220")
        assert lca == "23"

    def test_same_code(self):
        lca = Neo4jClient.query_lowest_common_ancestor("238220", "238220")
        assert lca == "238220"

    def test_different_sectors(self):
        lca = Neo4jClient.query_lowest_common_ancestor("238220", "541511")
        assert lca is None

    def test_6_digit_prefix_match(self):
        lca = Neo4jClient.query_lowest_common_ancestor("23822011", "23822099")
        assert lca == "238220"  # shared prefix is 6 digits

    def test_3_digit_prefix_match(self):
        lca = Neo4jClient.query_lowest_common_ancestor("238220", "238999")
        assert lca == "238"
