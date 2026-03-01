"""Tests for candidate_tools — find_candidates, compare_fields, semantic_similarity."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from tools.candidate_tools import find_candidates, compare_fields, semantic_similarity


def _make_ctx(app_context):
    """Build a mock MCP Context with lifespan_context."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context = app_context
    return ctx


@pytest.mark.asyncio
async def test_find_candidates_returns_matches(app_context, seeded_neo4j, sample_persona):
    """find_candidates should return the seeded golden record when bucket keys overlap."""
    app_context.neo4j = seeded_neo4j
    ctx = _make_ctx(app_context)

    result = await find_candidates(
        orphan_persona=sample_persona.model_dump(),
        max_candidates=10,
        ctx=ctx,
    )

    assert "candidates" in result
    assert "bucket_stats" in result
    assert result["bucket_stats"]["total_buckets_checked"] > 0


@pytest.mark.asyncio
async def test_find_candidates_empty_db(app_context, sample_persona):
    """find_candidates on an empty DB should return no candidates."""
    ctx = _make_ctx(app_context)

    result = await find_candidates(
        orphan_persona=sample_persona.model_dump(),
        max_candidates=10,
        ctx=ctx,
    )

    assert result["candidates"] == []


@pytest.mark.asyncio
async def test_compare_fields_disqualify_ein(app_context, sample_persona):
    """compare_fields should disqualify when EINs differ."""
    ctx = _make_ctx(app_context)

    candidate = {
        "persona": {
            "identity": {"normalized_name": "Bob's Plumbing LLC", "ein_clean": "999999999"},
            "location": {"state": "TX"},
        },
        "name_variants": [],
    }

    result = await compare_fields(
        orphan_persona=sample_persona.model_dump(),
        candidate=candidate,
        ctx=ctx,
    )

    assert result["disqualified"] is True
    assert "EIN" in result["disqualification_reason"]


@pytest.mark.asyncio
async def test_compare_fields_disqualify_state(app_context, sample_persona):
    """compare_fields should disqualify when states differ."""
    ctx = _make_ctx(app_context)

    candidate = {
        "persona": {
            "identity": {"normalized_name": "Bob's Plumbing LLC"},
            "location": {"state": "CA"},
        },
        "name_variants": [],
    }

    result = await compare_fields(
        orphan_persona=sample_persona.model_dump(),
        candidate=candidate,
        ctx=ctx,
    )

    assert result["disqualified"] is True
    assert "state" in result["disqualification_reason"].lower()


@pytest.mark.asyncio
async def test_compare_fields_same_entity(app_context, sample_persona):
    """compare_fields with identical personas should score high."""
    ctx = _make_ctx(app_context)

    candidate = {
        "persona": sample_persona.model_dump(),
        "name_variants": ["Bob's Plumbing LLC"],
    }

    result = await compare_fields(
        orphan_persona=sample_persona.model_dump(),
        candidate=candidate,
        ctx=ctx,
    )

    assert result["disqualified"] is False
    assert result["composite"] > 0.5


@pytest.mark.asyncio
async def test_semantic_similarity(app_context, sample_persona):
    """semantic_similarity should return scores between 0 and 1."""
    ctx = _make_ctx(app_context)

    candidate = {
        "persona": sample_persona.model_dump(),
    }

    result = await semantic_similarity(
        orphan_persona=sample_persona.model_dump(),
        candidate=candidate,
        ctx=ctx,
    )

    assert "composite_similarity" in result
    assert 0.0 <= result["composite_similarity"] <= 1.0
    assert "model_used" in result
