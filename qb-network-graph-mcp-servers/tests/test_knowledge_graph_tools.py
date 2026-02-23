"""Tests for knowledge_graph_tools — query_ontology, check_shared_context, etc."""
import pytest
from unittest.mock import MagicMock
from tools.knowledge_graph_tools import (
    query_ontology, check_shared_context,
    write_entity_triples, write_merge_redirect,
    _fallback_ontology,
)


def _make_ctx(app_context):
    ctx = MagicMock()
    ctx.request_context.lifespan_context = app_context
    return ctx


class TestFallbackOntology:
    """Test the conservative fallback when GraphDB is unavailable."""

    def test_same_subsector(self):
        result = _fallback_ontology("238220", "238210")
        assert result["related"] is True
        assert result["relationship_type"] == "SIBLING"

    def test_same_sector(self):
        result = _fallback_ontology("238220", "236220")
        assert result["related"] is True
        assert result["relationship_type"] == "ANCESTOR"

    def test_different_sectors(self):
        result = _fallback_ontology("238220", "424710")
        assert result["related"] is False

    def test_missing_codes(self):
        result = _fallback_ontology("", "238220")
        assert result["related"] is False


@pytest.mark.asyncio
async def test_query_ontology_fallback(app_context):
    """query_ontology should fall back when GraphDB is unavailable."""
    ctx = _make_ctx(app_context)

    result = await query_ontology(
        query_type="INDUSTRY_RELATION",
        code_a="238220",
        code_b="238210",
        ctx=ctx,
    )

    # GraphDB is unavailable in test, so fallback should kick in
    assert "related" in result
    assert "semantic_distance" in result


@pytest.mark.asyncio
async def test_check_shared_context_unavailable(app_context):
    """check_shared_context should return empty when GraphDB unavailable."""
    ctx = _make_ctx(app_context)

    result = await check_shared_context(
        entity_a_id="G-test0001",
        known_counterparties=["G-other01"],
        ctx=ctx,
    )

    assert result["shared_neighbors"] == []
    assert "unavailable" in result["supporting_evidence"].lower()


@pytest.mark.asyncio
async def test_write_entity_triples_unavailable(app_context):
    """write_entity_triples should return fallback when GraphDB unavailable."""
    ctx = _make_ctx(app_context)

    result = await write_entity_triples(
        entity_id="G-test0001",
        attrs={"canonical_name": "Test Entity", "entity_type": "PHANTOM"},
        ctx=ctx,
    )

    assert result["success"] is False
    assert result["fallback_to_changelog"] is True


@pytest.mark.asyncio
async def test_write_merge_redirect_unavailable(app_context):
    """write_merge_redirect should return fallback when GraphDB unavailable."""
    ctx = _make_ctx(app_context)

    result = await write_merge_redirect(
        survivor_id="G-surv",
        absorbed_id="G-abso",
        survivor_updates={"name_variants": [], "unspsc_codes": []},
        ctx=ctx,
    )

    assert result["success"] is False
    assert result["fallback_to_changelog"] is True
