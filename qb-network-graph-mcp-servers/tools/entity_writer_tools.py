"""
Entity writer tools — thin wrappers delegating to EntityWriterService.

5 tools: merge_into_golden_record, create_golden_record, submit_for_review,
         merge_golden_records, log_decision
"""
from __future__ import annotations

import json

from mcp.server.fastmcp import Context

from app import mcp, AppContext


@mcp.tool()
async def merge_into_golden_record(
    orphan_record_id: str,
    orphan_persona: dict,
    golden_record_id: str,
    merge_reasoning: dict,
    company_id: str,
    record_type: str = "vendor",
    ctx: Context = None,
) -> dict:
    """Merge an orphan record into an existing golden record.

    Applies survivorship rules (fill-in-the-blanks), updates the golden record
    and returns computed data for the Classifier Orchestrator to persist via Paimon.

    Args:
        orphan_record_id: Record ID of the orphan being merged.
        orphan_persona: Classified persona dict of the orphan.
        golden_record_id: Target golden record to merge into.
        merge_reasoning: Dict with reasoning, confidence, dimension_scores.
        company_id: Company ID that owns this record (used for relationship edges).
        record_type: Type of record — 'vendor' or 'customer' (default 'vendor').

    Returns:
        Dict with 'success', 'golden_record_id', before/after snapshots, sync_status.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return await app.entity_writer_service.merge_into(
        orphan_record_id, orphan_persona, golden_record_id,
        merge_reasoning, company_id, record_type,
    )


@mcp.tool()
async def create_golden_record(
    orphan_record_id: str,
    orphan_persona: dict,
    creation_reasoning: dict,
    company_id: str,
    record_type: str = "vendor",
    ctx: Context = None,
) -> dict:
    """Create a new golden record from an unmatched orphan.

    Generates a new golden record ID, builds bucket keys, persists to Neo4j
    and returns computed data for the Classifier Orchestrator to persist via Paimon.

    Args:
        orphan_record_id: Record ID of the orphan.
        orphan_persona: Classified persona dict of the orphan.
        creation_reasoning: Dict with reasoning for why this is a new entity.
        company_id: Company ID that owns this record (used for relationship edges).
        record_type: Type of record — 'vendor' or 'customer' (default 'vendor').

    Returns:
        Dict with 'success', 'golden_record_id', 'bucket_keys', sync_status.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return await app.entity_writer_service.create(
        orphan_record_id, orphan_persona, creation_reasoning,
        company_id, record_type,
    )


@mcp.tool()
async def submit_for_review(
    orphan_record_id: str,
    orphan_persona: dict,
    candidate_golden_record_id: str,
    review_reasoning: dict,
    company_id: str,
    record_type: str = "vendor",
    ctx: Context = None,
) -> dict:
    """Submit an ambiguous match to the human review queue.

    Creates a provisional golden record in Neo4j and a pending resolution
    entry in MySQL (OLTP work queue).

    Args:
        orphan_record_id: Record ID of the orphan.
        orphan_persona: Classified persona dict of the orphan.
        candidate_golden_record_id: Best candidate golden record ID.
        review_reasoning: Dict with confidence, dimension_scores, reasoning, key_uncertainty.
        company_id: Company ID that owns this record (used for relationship edges).
        record_type: Type of record — 'vendor' or 'customer' (default 'vendor').

    Returns:
        Dict with 'success', 'provisional_golden_record_id', 'pending_match_id', sync_status.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return await app.entity_writer_service.submit_for_review(
        orphan_record_id, orphan_persona, candidate_golden_record_id,
        review_reasoning, company_id, record_type,
    )


@mcp.tool()
async def merge_golden_records(
    survivor_id: str,
    absorbed_id: str,
    merge_reasoning: dict,
    ctx: Context = None,
) -> dict:
    """Merge two existing golden records (re-evaluation trigger).

    Uses Neo4j multi-statement transaction: upsert survivor, merge edges,
    mark absorbed as MERGED, write audit. Returns computed data for Paimon persistence.

    Args:
        survivor_id: Preferred survivor golden record ID.
        absorbed_id: Golden record ID to be absorbed/merged.
        merge_reasoning: Dict with confidence, dimension_scores, reasoning, key_factors.

    Returns:
        Dict with 'success', 'survivor_id', 'absorbed_id', before/after snapshots, sync_status.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return await app.entity_writer_service.merge_golden_records(
        survivor_id, absorbed_id, merge_reasoning,
    )


@mcp.tool()
async def log_decision(
    event_id: str,
    record_id: str,
    decision: str,
    target_golden_record_id: str | None,
    confidence: float,
    dimension_scores: dict,
    reasoning: str,
    key_factors: list[str],
    evaluation_chain: list[dict],
    agent_metadata: dict,
    ctx: Context = None,
) -> str:
    """Log an entity resolution decision to the audit trail.

    Every agent invocation should call this to record the decision,
    scores, reasoning, and metadata for compliance and debugging.

    Args:
        event_id: Unique event ID for this resolution.
        record_id: Record ID being resolved.
        decision: MERGE, NEW_ENTITY, REVIEW, or NO_MERGE_FOUND.
        target_golden_record_id: Golden record ID if MERGE/REVIEW.
        confidence: Confidence score 0.0-1.0.
        dimension_scores: Per-dimension scores dict.
        reasoning: Human-readable reasoning string.
        key_factors: List of key factors that influenced the decision.
        evaluation_chain: List of evaluation step dicts.
        agent_metadata: Additional metadata (trigger_type, candidates_evaluated, etc).

    Returns:
        Audit ID string.
    """
    app: AppContext = ctx.request_context.lifespan_context
    result = app.entity_writer_service.log_decision(
        event_id, record_id, decision, target_golden_record_id,
        confidence, dimension_scores, reasoning, key_factors,
        evaluation_chain, agent_metadata,
    )
    return json.dumps(result, default=str)
