"""
Tests for mcp/knowledge_graph.py.
"""
import pytest
from unittest.mock import MagicMock
from config import KnowledgeGraphConfig
from clients.graphdb_client import GraphDBClient
from mcp.knowledge_graph import KnowledgeGraphServer


@pytest.fixture
def unavailable_kg():
    gdb = GraphDBClient(KnowledgeGraphConfig())
    gdb._available = False
    return KnowledgeGraphServer(gdb)


@pytest.fixture
def available_kg():
    gdb = MagicMock(spec=GraphDBClient)
    gdb.available = True
    return KnowledgeGraphServer(gdb)


# ══════════════════════════════════════════════════════════════
# TestIndustryRelation
# ══════════════════════════════════════════════════════════════

class TestIndustryRelation:
    def test_same_codes_distance_0(self, available_kg):
        available_kg._gdb.query_naics_hierarchy.return_value = ["238220", "238", "23"]
        available_kg._gdb.query_lowest_common_ancestor.return_value = "238220"
        available_kg._gdb.query_cross_taxonomy_links.return_value = []
        result = available_kg.query_ontology("INDUSTRY_RELATION", "238220", "238220")
        assert result["semantic_distance"] == 0.0
        assert result["relationship_type"] == "SAME"

    def test_sibling_lca_3_plus(self, available_kg):
        available_kg._gdb.query_naics_hierarchy.return_value = ["238220", "238", "23"]
        available_kg._gdb.query_lowest_common_ancestor.return_value = "238"  # 3 chars
        available_kg._gdb.query_cross_taxonomy_links.return_value = []
        result = available_kg.query_ontology("INDUSTRY_RELATION", "238220", "238210")
        assert result["relationship_type"] == "SIBLING"
        assert result["semantic_distance"] == 0.2

    def test_ancestor_lca_2(self, available_kg):
        available_kg._gdb.query_naics_hierarchy.return_value = ["23"]
        available_kg._gdb.query_lowest_common_ancestor.return_value = "23"  # 2 chars
        available_kg._gdb.query_cross_taxonomy_links.return_value = []
        result = available_kg.query_ontology("INDUSTRY_RELATION", "238220", "236110")
        assert result["relationship_type"] == "ANCESTOR"
        assert result["semantic_distance"] == 0.4

    def test_cross_taxonomy_links(self, available_kg):
        available_kg._gdb.query_naics_hierarchy.return_value = []
        available_kg._gdb.query_lowest_common_ancestor.return_value = None
        available_kg._gdb.query_cross_taxonomy_links.return_value = [
            {"code": "40171500", "label": "Pipe fittings"},
        ]
        result = available_kg.query_ontology("INDUSTRY_RELATION", "238220", "423710")
        assert result["relationship_type"] == "CROSS_TAXONOMY_LINK"
        assert result["semantic_distance"] == 0.35

    def test_unrelated(self, available_kg):
        available_kg._gdb.query_naics_hierarchy.return_value = []
        available_kg._gdb.query_lowest_common_ancestor.return_value = None
        available_kg._gdb.query_cross_taxonomy_links.return_value = []
        result = available_kg.query_ontology("INDUSTRY_RELATION", "111", "999")
        assert result["relationship_type"] == "UNRELATED"
        assert result["semantic_distance"] == 0.8

    def test_related_threshold(self, available_kg):
        available_kg._gdb.query_naics_hierarchy.return_value = []
        available_kg._gdb.query_lowest_common_ancestor.return_value = "238"
        available_kg._gdb.query_cross_taxonomy_links.return_value = []
        result = available_kg.query_ontology("INDUSTRY_RELATION", "238220", "238210")
        assert result["related"] is True  # distance 0.2 < 0.7


# ══════════════════════════════════════════════════════════════
# TestExplanation
# ══════════════════════════════════════════════════════════════

class TestExplanation:
    def test_same_explanation(self, available_kg):
        available_kg._gdb.query_naics_hierarchy.return_value = []
        available_kg._gdb.query_lowest_common_ancestor.return_value = "238220"
        available_kg._gdb.query_cross_taxonomy_links.return_value = []
        result = available_kg.query_ontology("INDUSTRY_RELATION", "238220", "238220")
        assert "Same NAICS" in result["explanation"]

    def test_sibling_explanation(self, available_kg):
        available_kg._gdb.query_naics_hierarchy.return_value = []
        available_kg._gdb.query_lowest_common_ancestor.return_value = "238"
        available_kg._gdb.query_cross_taxonomy_links.return_value = []
        result = available_kg.query_ontology("INDUSTRY_RELATION", "238220", "238210")
        assert "subsector" in result["explanation"].lower()

    def test_cross_taxonomy_explanation(self, available_kg):
        available_kg._gdb.query_naics_hierarchy.return_value = []
        available_kg._gdb.query_lowest_common_ancestor.return_value = None
        available_kg._gdb.query_cross_taxonomy_links.return_value = [
            {"code": "40171500", "label": "Pipe fittings"},
        ]
        result = available_kg.query_ontology("INDUSTRY_RELATION", "238220", "423710")
        assert "Pipe fittings" in result["explanation"]

    def test_unrelated_explanation(self, available_kg):
        available_kg._gdb.query_naics_hierarchy.return_value = []
        available_kg._gdb.query_lowest_common_ancestor.return_value = None
        available_kg._gdb.query_cross_taxonomy_links.return_value = []
        result = available_kg.query_ontology("INDUSTRY_RELATION", "111", "999")
        assert "unrelated" in result["explanation"].lower()


# ══════════════════════════════════════════════════════════════
# TestCommodityRelation
# ══════════════════════════════════════════════════════════════

class TestCommodityRelation:
    def test_identical_codes(self, available_kg):
        result = available_kg.query_ontology("COMMODITY_RELATION", "40171500", "40171500")
        assert result["relationship_type"] == "SAME"
        assert result["semantic_distance"] == 0.0

    def test_prefix_match(self, available_kg):
        result = available_kg.query_ontology("COMMODITY_RELATION", "40171500", "40171501")
        assert result["semantic_distance"] < 0.5

    def test_unrelated_commodities(self, available_kg):
        result = available_kg.query_ontology("COMMODITY_RELATION", "11111111", "99999999")
        assert result["related"] is False


# ══════════════════════════════════════════════════════════════
# TestGeoContainment
# ══════════════════════════════════════════════════════════════

class TestGeoContainment:
    def test_same_case_insensitive(self, available_kg):
        result = available_kg.query_ontology("GEO_CONTAINMENT", "Austin", "austin")
        assert result["related"] is True

    def test_different(self, available_kg):
        result = available_kg.query_ontology("GEO_CONTAINMENT", "Austin", "Dallas")
        assert result["related"] is False


# ══════════════════════════════════════════════════════════════
# TestFallbackOntology
# ══════════════════════════════════════════════════════════════

class TestFallbackOntology:
    def test_4_digit_prefix(self, unavailable_kg):
        result = unavailable_kg.query_ontology("INDUSTRY_RELATION", "238220", "238210")
        assert result["related"] is True
        assert result["relationship_type"] == "SIBLING"

    def test_2_digit_prefix(self, unavailable_kg):
        result = unavailable_kg.query_ontology("INDUSTRY_RELATION", "238220", "236110")
        assert result["related"] is True
        assert result["relationship_type"] == "ANCESTOR"

    def test_no_prefix(self, unavailable_kg):
        result = unavailable_kg.query_ontology("INDUSTRY_RELATION", "111111", "999999")
        assert result["related"] is False
        assert result["relationship_type"] == "UNRELATED"

    def test_missing_codes(self, unavailable_kg):
        result = unavailable_kg.query_ontology("INDUSTRY_RELATION", "", "")
        assert result["related"] is False


# ══════════════════════════════════════════════════════════════
# TestSharedContext
# ══════════════════════════════════════════════════════════════

class TestSharedContext:
    def test_graphdb_unavailable(self, unavailable_kg):
        result = unavailable_kg.check_shared_context("G-001", ["G-002"])
        assert result["shared_neighbors"] == []
        assert "unavailable" in result["supporting_evidence"].lower()

    def test_no_shared_neighbors(self, available_kg):
        available_kg._gdb.query_shared_neighbors.return_value = []
        result = available_kg.check_shared_context("G-001", ["G-002"])
        assert result["shared_neighbors"] == []
        assert result["industry_coherence"] == 0.0


# ══════════════════════════════════════════════════════════════
# TestWriteTriples
# ══════════════════════════════════════════════════════════════

class TestWriteTriples:
    def test_unavailable_fallback(self, unavailable_kg):
        result = unavailable_kg.write_entity_triples("G-001", {"canonical_name": "Test"})
        assert result["success"] is False
        assert result["fallback_to_changelog"] is True

    def test_available_delegates_to_graphdb(self, available_kg):
        available_kg._gdb.create_entity_triples.return_value = 5
        result = available_kg.write_entity_triples("G-001", {"canonical_name": "Test"})
        assert result["success"] is True
        assert result["triples_written"] == 5


# ══════════════════════════════════════════════════════════════
# TestWriteMergeRedirect
# ══════════════════════════════════════════════════════════════

class TestWriteMergeRedirect:
    def test_unavailable_fallback(self, unavailable_kg):
        result = unavailable_kg.write_merge_redirect("G-surv", "G-abso", {})
        assert result["success"] is False
        assert result["fallback_to_changelog"] is True

    def test_available_delegates(self, available_kg):
        available_kg._gdb.write_merge_redirect.return_value = {
            "triples_migrated": 1,
            "triples_created": 2,
            "triples_deleted": 1,
            "redirect_created": True,
        }
        result = available_kg.write_merge_redirect("G-surv", "G-abso", {"name_variants": ["V"]})
        assert result["success"] is True
        assert result["redirect_created"] is True
