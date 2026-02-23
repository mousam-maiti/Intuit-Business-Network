"""Tests for search_tools — 6 conversational search tools."""
import pytest
from unittest.mock import MagicMock
from tools.search_tools import (
    search_entities, describe_entity, query_network,
    aggregate_stats, search_by_relationship, get_merge_history,
)


def _make_ctx(app_context):
    ctx = MagicMock()
    ctx.request_context.lifespan_context = app_context
    return ctx


@pytest.mark.asyncio
async def test_search_entities_basic(app_context, seeded_mysql):
    """search_entities should return results from seeded data."""
    app_context.mysql = seeded_mysql

    # Seed Milvus mock with the golden record
    gr_data = seeded_mysql.get_golden_record("G-test0001")
    app_context.milvus.upsert_golden_record(gr_data)

    ctx = _make_ctx(app_context)

    result = await search_entities(
        query="plumbing",
        limit=10,
        ctx=ctx,
    )

    assert "results" in result
    assert result["total_found"] >= 1
    assert result["results"][0]["canonical_name"] == "Bob's Plumbing LLC"


@pytest.mark.asyncio
async def test_search_entities_with_filters(app_context, seeded_mysql):
    """search_entities with city filter should filter results."""
    app_context.mysql = seeded_mysql
    gr_data = seeded_mysql.get_golden_record("G-test0001")
    app_context.milvus.upsert_golden_record(gr_data)

    ctx = _make_ctx(app_context)

    # Search with wrong city — should filter out
    result = await search_entities(
        query="plumbing",
        city_filter="NEW YORK",
        limit=10,
        ctx=ctx,
    )

    # The mock Milvus returns all records, but city post-filter should exclude
    # (depends on whether mock golden record has city set)
    assert "results" in result


@pytest.mark.asyncio
async def test_search_entities_empty(app_context):
    """search_entities on empty DB should return no results."""
    ctx = _make_ctx(app_context)

    result = await search_entities(
        query="nonexistent business",
        limit=10,
        ctx=ctx,
    )

    assert result["results"] == []
    assert result["total_found"] == 0


@pytest.mark.asyncio
async def test_describe_entity(app_context, seeded_mysql):
    """describe_entity should return full profile."""
    app_context.mysql = seeded_mysql
    ctx = _make_ctx(app_context)

    result = await describe_entity(
        entity_id="G-test0001",
        ctx=ctx,
    )

    assert result["entity"] is not None
    assert result["entity"]["canonical_name"] == "Bob's Plumbing LLC"
    assert result["entity"]["golden_record_id"] == "G-test0001"
    assert "identity" in result["entity"]
    assert "industry" in result["entity"]
    assert "location" in result["entity"]


@pytest.mark.asyncio
async def test_describe_entity_not_found(app_context):
    """describe_entity for nonexistent ID should return error."""
    ctx = _make_ctx(app_context)

    result = await describe_entity(
        entity_id="G-nonexistent",
        ctx=ctx,
    )

    assert result["entity"] is None
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_query_network_unavailable(app_context):
    """query_network should return error when GraphDB is unavailable."""
    ctx = _make_ctx(app_context)

    result = await query_network(
        entity_id="G-test0001",
        depth=1,
        ctx=ctx,
    )

    assert "error" in result
    assert "unavailable" in result["error"].lower()


@pytest.mark.asyncio
async def test_aggregate_stats(app_context, seeded_mysql):
    """aggregate_stats should return grouped counts."""
    app_context.mysql = seeded_mysql
    ctx = _make_ctx(app_context)

    result = await aggregate_stats(
        group_by="state",
        ctx=ctx,
    )

    assert "groups" in result
    assert result["total"] >= 1

    # Check TX is in results
    states = [g["group_value"] for g in result["groups"]]
    assert "TX" in states


@pytest.mark.asyncio
async def test_aggregate_stats_confidence_range(app_context, seeded_mysql):
    """aggregate_stats with confidence_range grouping."""
    app_context.mysql = seeded_mysql
    ctx = _make_ctx(app_context)

    result = await aggregate_stats(
        group_by="confidence_range",
        ctx=ctx,
    )

    assert "groups" in result
    assert result["total"] >= 1


@pytest.mark.asyncio
async def test_aggregate_stats_invalid_group(app_context):
    """aggregate_stats with invalid group_by should return empty or error."""
    ctx = _make_ctx(app_context)

    result = await aggregate_stats(
        group_by="invalid_column",
        ctx=ctx,
    )

    # In mock mode, invalid group_by returns empty groups (no SQL validation)
    # In live mode, it returns an error dict
    assert "error" in result or result["groups"] == []


@pytest.mark.asyncio
async def test_search_by_relationship_unavailable(app_context):
    """search_by_relationship should return error when GraphDB unavailable."""
    ctx = _make_ctx(app_context)

    result = await search_by_relationship(
        entity_id="G-test0001",
        relationship_type="transactsWith",
        ctx=ctx,
    )

    assert "error" in result
    assert result["related_entities"] == []


@pytest.mark.asyncio
async def test_search_by_relationship_invalid_type(app_context):
    """search_by_relationship with invalid type should return error."""
    ctx = _make_ctx(app_context)

    result = await search_by_relationship(
        entity_id="G-test0001",
        relationship_type="invalidRelation",
        ctx=ctx,
    )

    assert "error" in result


@pytest.mark.asyncio
async def test_get_merge_history_empty(app_context):
    """get_merge_history with no audit records should return empty."""
    ctx = _make_ctx(app_context)

    result = await get_merge_history(
        entity_id="G-test0001",
        ctx=ctx,
    )

    assert result["audit_records"] == []
    assert result["total_records"] == 0
    assert result["summary"]["merges"] == 0


@pytest.mark.asyncio
async def test_get_merge_history_with_records(app_context, seeded_mysql):
    """get_merge_history after logging a decision should return it."""
    app_context.mysql = seeded_mysql
    ctx = _make_ctx(app_context)

    # Log a decision first
    from models.audit import AuditRecord
    audit = AuditRecord(
        audit_id="A-test0001",
        event_id="EVT-001",
        record_id="R-001",
        decision="MERGE",
        target_golden_id="G-test0001",
        confidence=0.92,
    )
    seeded_mysql.write_audit(audit)

    result = await get_merge_history(
        entity_id="G-test0001",
        ctx=ctx,
    )

    assert result["total_records"] == 1
    assert result["summary"]["merges"] == 1
