"""
Search tools — thin wrappers delegating to SearchService + KnowledgeGraphService.

8 tools: search_entities, describe_entity, query_network, aggregate_stats,
         search_by_relationship, get_company_connections, get_merge_history,
         traverse_supply_chain
"""
from __future__ import annotations

from mcp.server.fastmcp import Context

from app import mcp, AppContext


@mcp.tool()
async def search_entities(
    query: str,
    naics_filter: str = None,
    state_filter: str = None,
    city_filter: str = None,
    min_confidence: float = None,
    limit: int = 10,
    ctx: Context = None,
) -> dict:
    """Search golden records using hybrid search: Neo4j name match + Neo4j vector search.

    Args:
        query: Natural language search query (e.g., "plumbing contractors in Texas").
        naics_filter: Optional NAICS code prefix to filter by.
        state_filter: Optional 2-letter state code.
        city_filter: Optional city name to filter by.
        min_confidence: Optional minimum confidence threshold.
        limit: Maximum results to return (default 10).

    Returns:
        Dict with 'results' list and 'total_found' count.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.search_service.search_entities(
        query, naics_filter, state_filter, city_filter, min_confidence, limit,
    )


@mcp.tool()
async def describe_entity(entity_id: str, ctx: Context = None) -> dict:
    """Get a full profile of a golden record entity.

    Args:
        entity_id: Golden record ID.

    Returns:
        Dict with 'entity' profile, 'neighbors' list.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.search_service.describe_entity(entity_id)


@mcp.tool()
async def query_network(
    entity_id: str, depth: int = 1, direction: str = "both", ctx: Context = None,
) -> dict:
    """Multi-hop graph traversal via transaction edges.

    Args:
        entity_id: Starting golden record ID.
        depth: How many hops to traverse (1-3, default 1).
        direction: 'outgoing', 'incoming', or 'both'.

    Returns:
        Dict with 'nodes' and 'edges' for the subgraph.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.knowledge_graph_service.query_network(entity_id, depth, direction)


@mcp.tool()
async def aggregate_stats(
    group_by: str, state_filter: str = None,
    naics_filter: str = None, min_confidence: float = None,
    ctx: Context = None,
) -> dict:
    """Aggregate golden record statistics by a grouping dimension.

    Args:
        group_by: Dimension to group by (state, industry, naics_sector, etc.).
        state_filter: Optional 2-letter state code.
        naics_filter: Optional NAICS code prefix.
        min_confidence: Optional minimum confidence threshold.

    Returns:
        Dict with 'groups' list of {group_value, count} and 'total' count.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.search_service.aggregate_stats(
        group_by, state_filter, naics_filter, min_confidence,
    )


@mcp.tool()
async def search_by_relationship(
    entity_id: str, relationship_type: str = "BUYS_FROM",
    company_id: str = None, ctx: Context = None,
) -> dict:
    """Find entities connected via a specific relationship type.

    Args:
        entity_id: Golden record ID to search from.
        relationship_type: Relationship to follow (default 'BUYS_FROM').
        company_id: Optional company ID (kept for API compatibility).

    Returns:
        Dict with 'related_entities' list.
    """
    app: AppContext = ctx.request_context.lifespan_context

    if not app.neo4j.available:
        return {"error": "Neo4j unavailable", "related_entities": [], "count": 0}

    allowed = {"BUYS_FROM", "SELLS_TO"}
    if relationship_type not in allowed:
        return {"error": f"Unsupported relationship_type: {relationship_type}. Allowed: {sorted(allowed)}"}

    neighbors = app.neo4j.get_entity_neighbors(entity_id, direction="outgoing", rel_type=relationship_type)
    related = []
    for n in neighbors:
        neighbor_id = n.get("id", "")
        if not neighbor_id:
            continue
        related.append({
            "entity_id": neighbor_id, "name": n.get("name", ""),
            "canonical_name": n.get("name", ""), "rel_type": n.get("rel_type", ""),
            "volume": float(n.get("volume") or 0),
        })
    return {
        "related_entities": related, "count": len(related),
        "source_entity": entity_id, "relationship_type": relationship_type, "source": "neo4j",
    }


@mcp.tool()
async def get_company_connections(
    company_id: str, connection_type: str = "all",
    sort_by: str = "volume", limit: int = 20, ctx: Context = None,
) -> dict:
    """Get vendors/customers for a specific company from Neo4j.

    Args:
        company_id: The company's ID.
        connection_type: Filter by type — 'vendor', 'customer', or 'all'.
        sort_by: Sort results by 'volume', 'count', or 'name'.
        limit: Maximum results to return (default 20).

    Returns:
        Dict with 'connections' list, 'total' count, and summary stats.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.search_service.get_company_connections(company_id, connection_type, sort_by, limit)


@mcp.tool()
async def get_merge_history(entity_id: str, limit: int = 50, ctx: Context = None) -> dict:
    """Retrieve the merge/resolution audit trail for a golden record.

    Args:
        entity_id: Golden record ID.
        limit: Maximum audit records to return (default 50).

    Returns:
        Dict with 'audit_records' list and summary counts.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return app.search_service.get_merge_history(entity_id, limit)


@mcp.tool()
async def traverse_supply_chain(
    start_entity_id: str, hops: list[str],
    max_per_hop: int = 5, min_volume: float = 0, ctx: Context = None,
) -> dict:
    """Directed multi-hop supply chain traversal via Neo4j.

    Args:
        start_entity_id: Starting entity (company or golden record ID).
        hops: List of directions for each hop, e.g. ["vendor", "client", "vendor"].
        max_per_hop: Maximum entities to follow per hop (default 5).
        min_volume: Minimum transaction volume to include.

    Returns:
        Dict with paths, nodes, edges, and supply chain insights.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return await app.knowledge_graph_service.traverse_supply_chain(
        start_entity_id, hops, max_per_hop, min_volume,
    )
