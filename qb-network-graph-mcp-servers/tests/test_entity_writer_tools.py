"""Tests for entity_writer_tools — merge, create, review, log_decision."""
import pytest
from unittest.mock import MagicMock
from tools.entity_writer_tools import (
    merge_into_golden_record, create_golden_record,
    submit_for_review, merge_golden_records, log_decision,
)


def _make_ctx(app_context):
    ctx = MagicMock()
    ctx.request_context.lifespan_context = app_context
    return ctx


@pytest.mark.asyncio
async def test_create_golden_record(app_context, sample_persona):
    """create_golden_record should create a new record in Neo4j mock."""
    ctx = _make_ctx(app_context)

    result = await create_golden_record(
        orphan_record_id="R-new-001",
        orphan_persona=sample_persona.model_dump(),
        creation_reasoning={"reasoning": "No match found"},
        ctx=ctx,
    )

    assert result["success"] is True
    assert result["golden_record_id"].startswith("G-")
    assert len(result["bucket_keys"]) > 0

    # Verify in Neo4j mock
    gr_data = app_context.neo4j.get_golden_record(result["golden_record_id"])
    assert gr_data is not None
    assert gr_data["canonical_name"] == "Bob's Plumbing LLC"


@pytest.mark.asyncio
async def test_merge_into_golden_record(app_context, seeded_neo4j, sample_persona):
    """merge_into_golden_record should update existing GR."""
    app_context.neo4j = seeded_neo4j
    ctx = _make_ctx(app_context)

    # Create a slightly different orphan
    orphan = sample_persona.model_dump()
    orphan["identity"]["normalized_name"] = "Bob Plumbing Services"

    result = await merge_into_golden_record(
        orphan_record_id="R-merge-001",
        orphan_persona=orphan,
        golden_record_id="G-test0001",
        merge_reasoning={"reasoning": "High confidence match", "confidence": 0.92},
        ctx=ctx,
    )

    assert result["success"] is True
    assert result["golden_record_id"] == "G-test0001"

    # Verify updated
    gr_data = app_context.neo4j.get_golden_record("G-test0001")
    assert gr_data["source_count"] == 4  # was 3, now +1


@pytest.mark.asyncio
async def test_merge_into_nonexistent(app_context, sample_persona):
    """merge_into_golden_record should fail for nonexistent GR."""
    ctx = _make_ctx(app_context)

    result = await merge_into_golden_record(
        orphan_record_id="R-x",
        orphan_persona=sample_persona.model_dump(),
        golden_record_id="G-nonexistent",
        merge_reasoning={},
        ctx=ctx,
    )

    assert result["success"] is False
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_submit_for_review(app_context, seeded_neo4j, sample_persona):
    """submit_for_review should create provisional GR + pending resolution."""
    app_context.neo4j = seeded_neo4j
    ctx = _make_ctx(app_context)

    result = await submit_for_review(
        orphan_record_id="R-review-001",
        orphan_persona=sample_persona.model_dump(),
        candidate_golden_record_id="G-test0001",
        review_reasoning={"confidence": 0.72, "reasoning": "Ambiguous name match"},
        ctx=ctx,
    )

    assert result["success"] is True
    assert result["provisional_golden_record_id"].startswith("G-")
    assert result["pending_match_id"].startswith("PR-")


@pytest.mark.asyncio
async def test_merge_golden_records(app_context, seeded_neo4j, sample_persona):
    """merge_golden_records should merge two existing GRs."""
    app_context.neo4j = seeded_neo4j
    ctx = _make_ctx(app_context)

    # Create a second golden record to merge
    from models.persona import GoldenRecord, ClassifiedPersona, IdentityDimension, LocationDimension
    gr2 = GoldenRecord(
        golden_record_id="G-test0002",
        canonical_name="Bobs Plumbing",
        persona=ClassifiedPersona(
            identity=IdentityDimension(normalized_name="Bobs Plumbing"),
            location=LocationDimension(state="TX"),
        ),
        source_count=1,
        source_records=["R-999"],
    )
    seeded_neo4j.upsert_entity(gr2.model_dump())

    result = await merge_golden_records(
        survivor_id="G-test0001",
        absorbed_id="G-test0002",
        merge_reasoning={"confidence": 0.90, "reasoning": "Same entity"},
        ctx=ctx,
    )

    assert result["success"] is True
    assert result["survivor_id"] == "G-test0001"


@pytest.mark.asyncio
async def test_log_decision(app_context):
    """log_decision should write an audit record to Neo4j."""
    ctx = _make_ctx(app_context)

    audit_id = await log_decision(
        event_id="EVT-001",
        record_id="R-001",
        decision="MERGE",
        target_golden_record_id="G-test0001",
        confidence=0.92,
        dimension_scores={"identity": 0.95, "industry": 0.80},
        reasoning="High confidence match",
        key_factors=["EIN exact match", "Same city"],
        evaluation_chain=[{"step": "find_candidates"}],
        agent_metadata={"trigger_type": "AI_AGENT", "candidates_evaluated": 5},
        ctx=ctx,
    )

    assert audit_id.startswith("A-")
    assert len(app_context.neo4j._mock_audit) == 1
