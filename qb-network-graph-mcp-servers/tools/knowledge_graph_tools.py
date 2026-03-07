"""
Knowledge graph tools — thin wrappers delegating to KnowledgeGraphService.

Tools: query_ontology, check_shared_context, batch_industry_filter,
       find_shortest_path, find_common_neighbors, detect_cluster, assess_risk_impact
"""
from __future__ import annotations

from mcp.server.fastmcp import Context

from app import mcp, AppContext


# ── Internal helper (used by candidate_tools.compare_fields) ──

def _query_ontology_internal(app: AppContext, query_type: str, code_a: str, code_b: str) -> dict:
    """Internal ontology query — called by compare_fields for cross-taxonomy links."""
    return app.knowledge_graph_service.query_ontology(query_type, code_a, code_b)


@mcp.tool()
async def query_ontology(
    query_type: str, code_a: str = "", code_b: str = "", ctx: Context = None,
) -> dict:
    """Query T-Box ontology for semantic relationships between NAICS/commodity/geo codes.

    Args:
        query_type: Type of query — INDUSTRY_RELATION, COMMODITY_RELATION, or GEO_CONTAINMENT.
        code_a: First NAICS/commodity/geo code.
        code_b: Second NAICS/commodity/geo code.

    Returns:
        Dict with 'related' bool, 'relationship_type', 'semantic_distance', and 'explanation'.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.knowledge_graph_service.query_ontology(query_type, code_a, code_b)


@mcp.tool()
async def check_shared_context(
    entity_a_id: str, known_counterparties: list[str], ctx: Context = None,
) -> dict:
    """Ontology-aware shared neighbor analysis.

    Args:
        entity_a_id: Golden record ID of the candidate entity.
        known_counterparties: List of golden record IDs that the orphan transacts with.

    Returns:
        Dict with 'shared_neighbors', 'industry_coherence', and 'supporting_evidence'.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.knowledge_graph_service.check_shared_context(entity_a_id, known_counterparties)


@mcp.tool()
async def batch_industry_filter(
    reference_naics: str, candidates: list[dict], ctx: Context = None,
) -> dict:
    """Check which candidates are related to a reference NAICS code via ontology.

    Args:
        reference_naics: The NAICS code representing the target industry.
        candidates: List of dicts with at least 'naics_code' and 'name' fields.

    Returns:
        Dict with 'matches' (related candidates) and 'unmatched_count'.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.knowledge_graph_service.batch_industry_filter(reference_naics, candidates)


@mcp.tool()
async def find_shortest_path(entity_a: str, entity_b: str, ctx: Context = None) -> dict:
    """Find the shortest connection path between any two entities.

    Args:
        entity_a: Golden record ID of the first entity.
        entity_b: Golden record ID of the second entity.

    Returns:
        Dict with 'chain', 'edges', 'hops', and 'duration_ms'.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.knowledge_graph_service.find_shortest_path(entity_a, entity_b)


@mcp.tool()
async def find_common_neighbors(
    entity_a_id: str, entity_b_id: str, limit: int = 20, ctx: Context = None,
) -> dict:
    """Find entities that are direct transaction partners of BOTH given entities.

    Args:
        entity_a_id: Golden record ID of the first entity.
        entity_b_id: Golden record ID of the second entity.
        limit: Maximum results to return (default 20).

    Returns:
        Dict with 'common_neighbors' list and 'count'.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.knowledge_graph_service.find_common_neighbors(entity_a_id, entity_b_id, limit)


@mcp.tool()
async def detect_cluster(entity_id: str, max_size: int = 20, ctx: Context = None) -> dict:
    """Discover the business cluster around an entity.

    Args:
        entity_id: Golden record ID of the center entity.
        max_size: Maximum cluster members to return (default 20).

    Returns:
        Dict with 'nodes', 'edges', 'density', 'center', and 'top_industries'.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.knowledge_graph_service.detect_cluster(entity_id, max_size)


@mcp.tool()
async def assess_risk_impact(entity_id: str, max_depth: int = 3, ctx: Context = None) -> dict:
    """Analyze downstream impact if an entity were to disappear from the network.

    Args:
        entity_id: Golden record ID of the entity to assess.
        max_depth: Maximum depth to trace dependencies (default 3).

    Returns:
        Dict with 'affected_entities', 'total_volume_at_risk', and 'concentration_warning'.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.knowledge_graph_service.assess_risk_impact(entity_id, max_depth)
