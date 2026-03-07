"""
Tests for clients/graphdb_client.py — mocks httpx.Client responses.
"""
import time
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from config import KnowledgeGraphConfig
from clients.graphdb_client import GraphDBClient, _esc


@pytest.fixture
def unavailable_client():
    c = GraphDBClient(KnowledgeGraphConfig())
    c._available = False
    return c


@pytest.fixture
def available_client():
    c = GraphDBClient(KnowledgeGraphConfig())
    c._available = True
    c._client = MagicMock()
    return c


def _sparql_response(bindings):
    """Build a mock SPARQL JSON response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "results": {"bindings": bindings}
    }
    resp.raise_for_status = MagicMock()
    return resp


# ══════════════════════════════════════════════════════════════
# TestUnavailable
# ══════════════════════════════════════════════════════════════

class TestUnavailable:
    def test_query_returns_empty(self, unavailable_client):
        assert unavailable_client.query("SELECT * WHERE {?s ?p ?o}") == []

    def test_update_returns_false(self, unavailable_client):
        assert unavailable_client.update("INSERT DATA { }") is False

    def test_available_property(self, unavailable_client):
        assert unavailable_client.available is False


# ══════════════════════════════════════════════════════════════
# TestQuery
# ══════════════════════════════════════════════════════════════

class TestQuery:
    def test_parses_sparql_results(self, available_client):
        bindings = [
            {"name": {"value": "Bob"}, "code": {"value": "238220"}},
            {"name": {"value": "Alice"}, "code": {"value": "423710"}},
        ]
        available_client._client.get.return_value = _sparql_response(bindings)
        results = available_client.query("SELECT ?name ?code WHERE { }")
        assert len(results) == 2
        assert results[0]["name"] == "Bob"
        assert results[1]["code"] == "423710"

    def test_empty_results(self, available_client):
        available_client._client.get.return_value = _sparql_response([])
        results = available_client.query("SELECT * WHERE { }")
        assert results == []

    def test_cache_hit(self, available_client):
        bindings = [{"x": {"value": "cached"}}]
        available_client._client.get.return_value = _sparql_response(bindings)
        sparql = "SELECT ?x WHERE { ?x a :Thing }"
        # First call — misses cache
        r1 = available_client.query(sparql, use_cache=True)
        # Second call — hits cache
        r2 = available_client.query(sparql, use_cache=True)
        assert r1 == r2
        assert available_client._client.get.call_count == 1  # Only 1 HTTP call

    def test_cache_miss_after_ttl(self, available_client):
        bindings = [{"x": {"value": "stale"}}]
        available_client._client.get.return_value = _sparql_response(bindings)
        sparql = "SELECT ?x WHERE { ?x a :Stale }"
        available_client.query(sparql, use_cache=True)
        # Force cache expiry by backdating
        available_client._cache[sparql] = (time.time() - 100000, available_client._cache[sparql][1])
        available_client.query(sparql, use_cache=True)
        assert available_client._client.get.call_count == 2

    def test_http_error(self, available_client):
        resp = MagicMock()
        resp.raise_for_status.side_effect = Exception("HTTP 500")
        available_client._client.get.return_value = resp
        results = available_client.query("SELECT * WHERE { }")
        assert results == []

    def test_network_error(self, available_client):
        available_client._client.get.side_effect = ConnectionError("Connection refused")
        results = available_client.query("SELECT * WHERE { }")
        assert results == []


# ══════════════════════════════════════════════════════════════
# TestUpdate
# ══════════════════════════════════════════════════════════════

class TestUpdate:
    def test_success(self, available_client):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        available_client._client.post.return_value = resp
        assert available_client.update("INSERT DATA { }") is True

    def test_http_error(self, available_client):
        resp = MagicMock()
        resp.raise_for_status.side_effect = Exception("HTTP 500")
        available_client._client.post.return_value = resp
        assert available_client.update("INSERT DATA { }") is False

    def test_network_error(self, available_client):
        available_client._client.post.side_effect = ConnectionError("Connection refused")
        assert available_client.update("INSERT DATA { }") is False


# ══════════════════════════════════════════════════════════════
# TestNAICSHierarchy
# ══════════════════════════════════════════════════════════════

class TestNAICSHierarchy:
    def test_extracts_codes(self, available_client):
        bindings = [
            {"ancestor": {"value": "http://qb.intuit.com/ontology/naics/238220"}},
            {"ancestor": {"value": "http://qb.intuit.com/ontology/naics/238"}},
            {"ancestor": {"value": "http://qb.intuit.com/ontology/naics/23"}},
        ]
        available_client._client.get.return_value = _sparql_response(bindings)
        codes = available_client.query_naics_hierarchy("238220")
        assert "238220" in codes
        assert "238" in codes
        assert "23" in codes

    def test_lca_found(self, available_client):
        bindings = [{"lca": {"value": "http://qb.intuit.com/ontology/naics/238"}}]
        available_client._client.get.return_value = _sparql_response(bindings)
        lca = available_client.query_lowest_common_ancestor("238220", "238210")
        assert lca == "238"

    def test_lca_none(self, available_client):
        available_client._client.get.return_value = _sparql_response([])
        lca = available_client.query_lowest_common_ancestor("111", "999")
        assert lca is None


# ══════════════════════════════════════════════════════════════
# TestCrossTaxonomy
# ══════════════════════════════════════════════════════════════

class TestCrossTaxonomy:
    def test_links_found(self, available_client):
        bindings = [
            {
                "link": {"value": "http://qb.intuit.com/ontology/unspsc/40171500"},
                "label": {"value": "Pipe fittings"},
            }
        ]
        available_client._client.get.return_value = _sparql_response(bindings)
        links = available_client.query_cross_taxonomy_links("238220", "423710")
        assert len(links) == 1
        assert links[0]["label"] == "Pipe fittings"

    def test_no_links(self, available_client):
        available_client._client.get.return_value = _sparql_response([])
        links = available_client.query_cross_taxonomy_links("111", "999")
        assert links == []


# ══════════════════════════════════════════════════════════════
# TestCreateEntityTriples
# ══════════════════════════════════════════════════════════════

class TestCreateEntityTriples:
    def test_full_attrs(self, available_client):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        available_client._client.post.return_value = resp
        count = available_client.create_entity_triples("G-001", {
            "canonical_name": "BOBS PLUMBING",
            "entity_type": "Phantom",
            "confidence": 0.75,
            "naics_codes": ["238220"],
            "unspsc_codes": ["40171500"],
            "geo_location": "austin",
            "name_variants": ["BP LLC"],
            "ein": "123456789",
        })
        assert count > 0

    def test_unavailable_returns_0(self, unavailable_client):
        count = unavailable_client.create_entity_triples("G-001", {"canonical_name": "Test"})
        assert count == 0


# ══════════════════════════════════════════════════════════════
# TestWriteMergeRedirect
# ══════════════════════════════════════════════════════════════

class TestWriteMergeRedirect:
    def test_four_step_merge(self, available_client):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        available_client._client.post.return_value = resp
        result = available_client.write_merge_redirect(
            "G-survivor", "G-absorbed",
            {"name_variants": ["VARIANT"], "unspsc_codes": ["401715"]},
        )
        assert result["redirect_created"] is True
        # Should have made 4 update calls
        assert available_client._client.post.call_count == 4


# ══════════════════════════════════════════════════════════════
# TestEscape
# ══════════════════════════════════════════════════════════════

class TestEscape:
    def test_quotes(self):
        assert _esc('Bob"s') == 'Bob\\"s'

    def test_backslash_and_newline(self):
        assert _esc("line1\nline2") == "line1\\nline2"
        assert _esc("back\\slash") == "back\\\\slash"
