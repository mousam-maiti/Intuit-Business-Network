"""
Candidate evaluation tools — thin wrappers delegating to CandidateService.

3 tools: find_candidates, compare_fields, semantic_similarity
"""
from __future__ import annotations

from mcp.server.fastmcp import Context

from app import mcp, AppContext


@mcp.tool()
async def find_candidates(
    orphan_persona: dict,
    max_candidates: int = 20,
    ctx: Context = None,
) -> dict:
    """Retrieve candidate golden records by persona-dimension bucket keys.

    Generates bucket keys from the orphan persona and queries Neo4j indexed
    Entity nodes to find matching golden records. Candidates are sorted by the
    number of shared bucket keys (more overlap = stronger signal).

    Args:
        orphan_persona: Classified persona dict with identity, industry, location, commodity, behavioral dimensions.
        max_candidates: Maximum number of candidates to return (default 20).

    Returns:
        Dict with 'candidates' list, 'bucket_stats', and 'duration_ms'.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.candidate_service.find_candidates(orphan_persona, max_candidates)


@mcp.tool()
async def compare_fields(
    orphan_persona: dict,
    candidate: dict,
    ctx: Context = None,
) -> dict:
    """Deterministic field-by-field comparison across 5 persona dimensions.

    Compares orphan persona against a candidate golden record across identity,
    industry, location, commodity, and behavioral dimensions. Uses adaptive
    weight redistribution when dimensions have insufficient data.

    Hard disqualifiers:
      - EIN mismatch (both present but different)
      - State mismatch (both present but different)

    Args:
        orphan_persona: Classified persona dict for the orphan record.
        candidate: Candidate dict with 'persona', 'name_variants' keys.

    Returns:
        ComparisonResult dict with per-dimension scores, composite score,
        weights used, and disqualification status.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.candidate_service.compare_fields(
        orphan_persona, candidate,
        ontology_query_fn=app.knowledge_graph_service.query_ontology,
    )


@mcp.tool()
async def semantic_similarity(
    orphan_persona: dict,
    candidate: dict,
    ctx: Context = None,
) -> dict:
    """Compute semantic similarity via embeddings (Gemini text-embedding-004).

    Called when compare_fields returns ambiguous scores (0.40-0.85).
    Computes per-dimension cosine similarity between orphan and candidate
    persona text representations.

    Args:
        orphan_persona: Classified persona dict for the orphan record.
        candidate: Candidate dict with 'persona' key.

    Returns:
        SimilarityResult dict with per-dimension similarities and composite score.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.candidate_service.semantic_similarity(orphan_persona, candidate)
