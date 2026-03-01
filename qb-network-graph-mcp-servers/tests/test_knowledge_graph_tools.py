"""Tests for knowledge_graph_tools — query_ontology, check_shared_context, batch_industry_filter."""
import pytest
from unittest.mock import MagicMock
from tools.knowledge_graph_tools import (
    query_ontology, check_shared_context, batch_industry_filter,
)


def _make_ctx(app_context):
    ctx = MagicMock()
    ctx.request_context.lifespan_context = app_context
    return ctx


class TestQueryOntologyIndustryRelation:
    """Test NAICS ontology queries (pure Python + Neo4j/static fallback)."""

    @pytest.mark.asyncio
    async def test_same_subsector(self, app_context):
        ctx = _make_ctx(app_context)
        result = await query_ontology(
            query_type="INDUSTRY_RELATION",
            code_a="238220",
            code_b="238210",
            ctx=ctx,
        )
        assert result["related"] is True
        assert result["relationship_type"] == "SIBLING"
        assert result["lowest_common_ancestor"] == "2382"

    @pytest.mark.asyncio
    async def test_same_sector(self, app_context):
        ctx = _make_ctx(app_context)
        result = await query_ontology(
            query_type="INDUSTRY_RELATION",
            code_a="238220",
            code_b="236220",
            ctx=ctx,
        )
        assert result["related"] is True
        assert result["relationship_type"] == "ANCESTOR"
        assert result["lowest_common_ancestor"] == "23"

    @pytest.mark.asyncio
    async def test_same_code(self, app_context):
        ctx = _make_ctx(app_context)
        result = await query_ontology(
            query_type="INDUSTRY_RELATION",
            code_a="238220",
            code_b="238220",
            ctx=ctx,
        )
        assert result["related"] is True
        assert result["relationship_type"] == "SAME"
        assert result["semantic_distance"] == 0.0

    @pytest.mark.asyncio
    async def test_different_sectors(self, app_context):
        ctx = _make_ctx(app_context)
        result = await query_ontology(
            query_type="INDUSTRY_RELATION",
            code_a="238220",
            code_b="541511",
            ctx=ctx,
        )
        assert result["related"] is False
        assert result["semantic_distance"] >= 0.7


class TestQueryOntologyCommodity:
    """Test commodity code relations."""

    @pytest.mark.asyncio
    async def test_same_commodity(self, app_context):
        ctx = _make_ctx(app_context)
        result = await query_ontology(
            query_type="COMMODITY_RELATION",
            code_a="301516",
            code_b="301516",
            ctx=ctx,
        )
        assert result["related"] is True
        assert result["relationship_type"] == "SAME"

    @pytest.mark.asyncio
    async def test_sibling_commodity(self, app_context):
        ctx = _make_ctx(app_context)
        result = await query_ontology(
            query_type="COMMODITY_RELATION",
            code_a="301516",
            code_b="301518",
            ctx=ctx,
        )
        assert result["related"] is True
        assert result["relationship_type"] == "SIBLING"

    @pytest.mark.asyncio
    async def test_unrelated_commodity(self, app_context):
        ctx = _make_ctx(app_context)
        result = await query_ontology(
            query_type="COMMODITY_RELATION",
            code_a="301516",
            code_b="721110",
            ctx=ctx,
        )
        assert result["related"] is False


class TestQueryOntologyGeo:
    """Test geo containment queries."""

    @pytest.mark.asyncio
    async def test_same_geo(self, app_context):
        ctx = _make_ctx(app_context)
        result = await query_ontology(
            query_type="GEO_CONTAINMENT",
            code_a="TX",
            code_b="TX",
            ctx=ctx,
        )
        assert result["related"] is True
        assert result["relationship_type"] == "SAME"

    @pytest.mark.asyncio
    async def test_different_geo(self, app_context):
        ctx = _make_ctx(app_context)
        result = await query_ontology(
            query_type="GEO_CONTAINMENT",
            code_a="TX",
            code_b="CA",
            ctx=ctx,
        )
        assert result["related"] is False


@pytest.mark.asyncio
async def test_check_shared_context_neo4j_unavailable(app_context):
    """check_shared_context should return empty when Neo4j unavailable."""
    ctx = _make_ctx(app_context)

    result = await check_shared_context(
        entity_a_id="G-test0001",
        known_counterparties=["G-other01"],
        ctx=ctx,
    )

    assert result["shared_neighbors"] == []
    assert "unavailable" in result["supporting_evidence"].lower()


@pytest.mark.asyncio
async def test_batch_industry_filter_same_sector(app_context):
    """batch_industry_filter should match candidates in same/related sectors."""
    ctx = _make_ctx(app_context)

    result = await batch_industry_filter(
        reference_naics="238220",
        candidates=[
            {"naics_code": "238210", "name": "Electrical Contractor", "golden_record_id": "G-001"},
            {"naics_code": "236220", "name": "Home Builder", "golden_record_id": "G-002"},
            {"naics_code": "541511", "name": "Software Dev", "golden_record_id": "G-003"},
        ],
        ctx=ctx,
    )

    assert result["total_candidates"] == 3
    assert result["match_count"] >= 2  # 238210 (SIBLING) and 236220 (SAME_SECTOR or ANCESTOR)
    matched_ids = [m["golden_record_id"] for m in result["matches"]]
    assert "G-001" in matched_ids  # Same subsector
    assert "G-002" in matched_ids  # Same sector


@pytest.mark.asyncio
async def test_batch_industry_filter_empty(app_context):
    """batch_industry_filter with no candidates should return empty."""
    ctx = _make_ctx(app_context)

    result = await batch_industry_filter(
        reference_naics="238220",
        candidates=[],
        ctx=ctx,
    )

    assert result["match_count"] == 0
    assert result["matches"] == []
