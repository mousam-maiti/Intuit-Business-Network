"""
Conversational search tools — 6 NEW tools for AI chat / agent discovery.

13. search_entities       — semantic/hybrid search over golden records
14. describe_entity       — full profile: MySQL + KG + neighbors
15. query_network         — multi-hop graph traversal
16. aggregate_stats       — GROUP BY queries
17. search_by_relationship — find entities by KG predicate
18. get_merge_history     — audit trail from resolution_audit
"""
from __future__ import annotations
import json
import logging

from mcp.server.fastmcp import Context

from app import mcp, AppContext

logger = logging.getLogger(__name__)


# ── Tool 13: search_entities ─────────────────────────────────

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
    """Search golden records using hybrid search: MySQL name match + Milvus vector search.

    Performs a 3-tier MySQL name lookup (exact → LIKE → FULLTEXT) first to catch
    precise name matches, then augments with Milvus vector similarity results.
    This ensures exact matches like "ALL PRO HVAC" are never missed.

    Args:
        query: Natural language search query (e.g., "plumbing contractors in Texas").
        naics_filter: Optional NAICS code prefix to filter by (e.g., "2382").
        state_filter: Optional 2-letter state code (e.g., "TX").
        city_filter: Optional city name to filter by (case-insensitive).
        min_confidence: Optional minimum confidence threshold (0.0-1.0).
        limit: Maximum results to return (default 10).

    Returns:
        Dict with 'results' list and 'total_found' count.
    """
    app: AppContext = ctx.request_context.lifespan_context

    results = []
    seen_ids = set()

    # ── Phase 1: MySQL name search (exact → LIKE → FULLTEXT) ──
    mysql_hits = app.mysql.search_by_name(
        query=query,
        state_filter=state_filter,
        city_filter=city_filter,
        naics_filter=naics_filter,
        min_confidence=min_confidence,
        limit=limit,
    )
    for hit in mysql_hits:
        gr_id = hit.get("golden_record_id", "")
        if gr_id and gr_id not in seen_ids:
            seen_ids.add(gr_id)
            results.append({
                "golden_record_id": gr_id,
                "canonical_name": hit.get("canonical_name", ""),
                "state": hit.get("state", ""),
                "city": hit.get("city", ""),
                "naics_code": hit.get("naics_code", ""),
                "naics_sector": hit.get("naics_sector", ""),
                "confidence": float(hit.get("confidence", 0)),
                "entity_type": hit.get("entity_type", ""),
                "source_count": int(hit.get("source_count", 1)),
                "similarity": float(hit.get("match_rank", 0.9)),
            })

    # ── Phase 2: Milvus vector search (fills remaining slots) ──
    if len(results) < limit:
        try:
            raw_results = app.milvus.search_by_text(
                query_text=query,
                state_filter=state_filter,
                naics_filter=naics_filter,
                top_k=limit * 3,
            )
            for hit in raw_results:
                if len(results) >= limit:
                    break
                gr_id = hit.get("golden_record_id", "")
                if not gr_id or gr_id in seen_ids:
                    continue
                seen_ids.add(gr_id)

                gr_data = app.mysql.get_golden_record(gr_id)
                if not gr_data:
                    continue

                if city_filter:
                    gr_city = (gr_data.get("city") or "").upper()
                    if gr_city != city_filter.upper():
                        continue
                if min_confidence is not None:
                    gr_conf = float(gr_data.get("confidence", 0))
                    if gr_conf < min_confidence:
                        continue

                results.append({
                    "golden_record_id": gr_id,
                    "canonical_name": gr_data.get("canonical_name", ""),
                    "state": gr_data.get("state", ""),
                    "city": gr_data.get("city", ""),
                    "naics_code": gr_data.get("naics_code", ""),
                    "naics_sector": gr_data.get("naics_sector", ""),
                    "confidence": float(gr_data.get("confidence", 0)),
                    "entity_type": gr_data.get("entity_type", ""),
                    "source_count": int(gr_data.get("source_count", 1)),
                    "similarity": hit.get("similarity"),
                })
        except Exception as e:
            logger.warning(f"Milvus search failed, using MySQL results only: {e}")

    return {
        "results": results,
        "total_found": len(results),
        "query": query,
        "filters_applied": {
            k: v for k, v in {
                "state": state_filter, "city": city_filter,
                "naics": naics_filter, "min_confidence": min_confidence,
            }.items() if v is not None
        },
    }


# ── Tool 14: describe_entity ────────────────────────────────

@mcp.tool()
async def describe_entity(
    entity_id: str,
    ctx: Context = None,
) -> dict:
    """Get a full profile of a golden record entity.

    Combines data from MySQL (golden record fields), KG (triples and graph
    neighbors), and Milvus (vector metadata) into a comprehensive profile.

    Args:
        entity_id: Golden record ID.

    Returns:
        Dict with 'entity' profile, 'neighbors' list, 'kg_available' flag.
    """
    app: AppContext = ctx.request_context.lifespan_context

    gr_data = app.mysql.get_golden_record(entity_id)
    if not gr_data:
        return {"error": f"Entity {entity_id} not found", "entity": None}

    # Parse persona for structured fields
    persona = gr_data.get("persona", {})
    if isinstance(persona, str):
        try:
            persona = json.loads(persona)
        except (json.JSONDecodeError, TypeError):
            persona = {}

    name_variants = gr_data.get("name_variants", [])
    if isinstance(name_variants, str):
        try:
            name_variants = json.loads(name_variants)
        except (json.JSONDecodeError, TypeError):
            name_variants = []

    profile = {
        "golden_record_id": entity_id,
        "canonical_name": gr_data.get("canonical_name", ""),
        "name_variants": name_variants,
        "status": gr_data.get("status", ""),
        "entity_type": gr_data.get("entity_type", ""),
        "confidence": float(gr_data.get("confidence", 0)),
        "source_count": int(gr_data.get("source_count", 1)),
        "identity": {
            "ein": gr_data.get("ein") or persona.get("identity", {}).get("ein_clean"),
            "phone": gr_data.get("phone_digits") or persona.get("identity", {}).get("phone_digits"),
            "email": gr_data.get("email") or persona.get("identity", {}).get("email"),
        },
        "industry": {
            "naics_code": gr_data.get("naics_code") or persona.get("industry", {}).get("naics_code"),
            "naics_sector": gr_data.get("naics_sector") or persona.get("industry", {}).get("naics_sector"),
            "naics_subsector": gr_data.get("naics_subsector") or persona.get("industry", {}).get("naics_subsector"),
        },
        "location": {
            "state": gr_data.get("state") or persona.get("location", {}).get("state"),
            "city": gr_data.get("city") or persona.get("location", {}).get("city_norm"),
            "zip5": gr_data.get("zip5") or persona.get("location", {}).get("zip5"),
            "zip3": gr_data.get("zip3") or persona.get("location", {}).get("zip3"),
        },
        "commodity": {
            "top_keywords": persona.get("commodity", {}).get("top_keywords", []),
            "service_categories": persona.get("commodity", {}).get("service_categories", []),
        },
        "behavioral": {
            "volume_bracket": gr_data.get("volume_bracket") or persona.get("behavioral", {}).get("volume_bracket"),
            "avg_transaction": gr_data.get("avg_transaction") or persona.get("behavioral", {}).get("avg_transaction"),
            "transaction_count": gr_data.get("transaction_count") or persona.get("behavioral", {}).get("transaction_count"),
        },
        "merged_into": gr_data.get("merged_into"),
        "created_at": gr_data.get("created_at"),
        "updated_at": gr_data.get("updated_at"),
    }

    # KG neighbors
    neighbors = []
    kg_available = app.graphdb.available
    if kg_available:
        raw_neighbors = app.graphdb.query_shared_neighbors(entity_id)
        for n in raw_neighbors:
            neighbors.append({
                "entity_id": n.get("neighbor", "").split("/")[-1],
                "name": n.get("name", ""),
                "naics": n.get("naics", ""),
            })

    return {
        "entity": profile,
        "neighbors": neighbors,
        "neighbor_count": len(neighbors),
        "kg_available": kg_available,
    }


# ── Tool 15: query_network ──────────────────────────────────

@mcp.tool()
async def query_network(
    entity_id: str,
    depth: int = 1,
    direction: str = "both",
    ctx: Context = None,
) -> dict:
    """Multi-hop graph traversal via qb:transactsWith edges.

    Explores the transaction network around an entity up to the specified depth.

    Args:
        entity_id: Starting golden record ID.
        depth: How many hops to traverse (1-3, default 1).
        direction: 'outgoing', 'incoming', or 'both' (default 'both').

    Returns:
        Dict with 'nodes' and 'edges' for the subgraph, plus 'depth_reached'.
    """
    app: AppContext = ctx.request_context.lifespan_context

    if not app.graphdb.available:
        return {"nodes": [], "edges": [], "depth_reached": 0,
                "error": "GraphDB unavailable — cannot traverse network"}

    depth = max(1, min(3, depth))  # Clamp to 1-3

    visited = set()
    nodes = []
    edges = []
    frontier = {entity_id}

    for current_depth in range(depth):
        next_frontier = set()
        for eid in frontier:
            if eid in visited:
                continue
            visited.add(eid)

            # Get neighbors from KG
            raw_neighbors = app.graphdb.query_shared_neighbors(eid)

            # Build node info
            gr_data = app.mysql.get_golden_record(eid)
            node_info = {
                "entity_id": eid,
                "canonical_name": gr_data.get("canonical_name", "") if gr_data else "",
                "depth": current_depth,
            }
            if gr_data:
                node_info["state"] = gr_data.get("state", "")
                node_info["naics_code"] = gr_data.get("naics_code", "")
                node_info["confidence"] = float(gr_data.get("confidence", 0))
            nodes.append(node_info)

            for n in raw_neighbors:
                neighbor_id = n.get("neighbor", "").split("/")[-1]
                if not neighbor_id:
                    continue

                edges.append({
                    "source": eid,
                    "target": neighbor_id,
                    "relationship": "transactsWith",
                    "target_name": n.get("name", ""),
                    "target_naics": n.get("naics", ""),
                })

                if neighbor_id not in visited:
                    next_frontier.add(neighbor_id)

        frontier = next_frontier
        if not frontier:
            break

    # Add final frontier nodes (leaf nodes without expansion)
    for eid in frontier:
        if eid not in visited:
            gr_data = app.mysql.get_golden_record(eid)
            nodes.append({
                "entity_id": eid,
                "canonical_name": gr_data.get("canonical_name", "") if gr_data else "",
                "depth": depth,
                "state": gr_data.get("state", "") if gr_data else "",
            })

    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "depth_reached": min(depth, len(visited)),
        "root_entity": entity_id,
    }


# ── Tool 16: aggregate_stats ────────────────────────────────

@mcp.tool()
async def aggregate_stats(
    group_by: str,
    state_filter: str = None,
    naics_filter: str = None,
    min_confidence: float = None,
    ctx: Context = None,
) -> dict:
    """Aggregate golden record statistics by a grouping dimension.

    Runs GROUP BY queries on the golden_records table to produce counts
    by state, industry, city, confidence range, etc.

    Args:
        group_by: Dimension to group by. One of: state, industry, naics_sector,
                  naics_subsector, city, volume_bracket, entity_type, confidence_range.
        state_filter: Optional 2-letter state code.
        naics_filter: Optional NAICS code prefix.
        min_confidence: Optional minimum confidence threshold.

    Returns:
        Dict with 'groups' list of {group_value, count} and 'total' count.
    """
    app: AppContext = ctx.request_context.lifespan_context

    groups = app.mysql.aggregate_golden_records(
        group_by=group_by,
        state_filter=state_filter,
        naics_filter=naics_filter,
        min_confidence=min_confidence,
    )

    # Check for error
    if groups and isinstance(groups[0], dict) and "error" in groups[0]:
        return groups[0]

    total = sum(g.get("count", 0) for g in groups)

    return {
        "groups": groups,
        "total": total,
        "group_by": group_by,
        "filters_applied": {
            k: v for k, v in {
                "state": state_filter, "naics": naics_filter,
                "min_confidence": min_confidence,
            }.items() if v is not None
        },
    }


# ── Tool 17: search_by_relationship ──────────────────────────

@mcp.tool()
async def search_by_relationship(
    entity_id: str,
    relationship_type: str = "transactsWith",
    company_id: str = None,
    ctx: Context = None,
) -> dict:
    """Find entities connected to a given entity via a specific KG predicate.

    Queries the knowledge graph for entities related to the given entity
    through the specified relationship type. If company_id is provided and
    GraphDB is unavailable, falls back to querying the MySQL relationships table.

    Args:
        entity_id: Golden record ID to search from.
        relationship_type: KG predicate to follow (default 'transactsWith').
            Supported: transactsWith, operatesIn, locatedIn, provides.
        company_id: Optional company ID to query MySQL relationships as fallback.

    Returns:
        Dict with 'related_entities' list and 'relationship_type'.
    """
    app: AppContext = ctx.request_context.lifespan_context

    # Try GraphDB first
    if app.graphdb.available:
        allowed = {"transactsWith", "operatesIn", "locatedIn", "provides"}
        if relationship_type not in allowed:
            return {"error": f"Unsupported relationship_type: {relationship_type}. "
                             f"Allowed: {sorted(allowed)}"}

        sparql = f"""
        PREFIX entity: <http://qb.intuit.com/entity/>
        PREFIX qb: <http://qb.intuit.com/ontology/>

        SELECT ?related ?name WHERE {{
            entity:{entity_id} qb:{relationship_type} ?related .
            OPTIONAL {{ ?related qb:canonicalName ?name }}
        }}
        """
        rows = app.graphdb.query(sparql)

        related = []
        for r in rows:
            rel_id = r.get("related", "").split("/")[-1]
            if not rel_id:
                continue

            entry = {
                "entity_id": rel_id,
                "name": r.get("name", ""),
            }

            # Enrich from MySQL
            gr_data = app.mysql.get_golden_record(rel_id)
            if gr_data:
                entry["canonical_name"] = gr_data.get("canonical_name", "")
                entry["state"] = gr_data.get("state", "")
                entry["naics_code"] = gr_data.get("naics_code", "")
                entry["confidence"] = float(gr_data.get("confidence", 0))

            related.append(entry)

        if related:
            return {
                "related_entities": related,
                "count": len(related),
                "source_entity": entity_id,
                "relationship_type": relationship_type,
                "source": "graphdb",
            }

    # Fallback: MySQL relationships table (company_id → golden records)
    lookup_id = company_id or entity_id
    rows = app.mysql.get_relationships(lookup_id)
    related = []
    for r in rows:
        related.append({
            "entity_id": r.get("target_entity_id", ""),
            "canonical_name": r.get("canonical_name", ""),
            "state": r.get("state", ""),
            "city": r.get("city", ""),
            "naics_code": r.get("naics_code", ""),
            "confidence": float(r.get("confidence", 0)),
            "transaction_volume": r.get("transaction_volume"),
            "transaction_count": r.get("transaction_count"),
        })

    return {
        "related_entities": related,
        "count": len(related),
        "source_entity": lookup_id,
        "relationship_type": relationship_type,
        "source": "mysql_relationships",
    }


# ── Tool 19: get_company_connections ─────────────────────────

@mcp.tool()
async def get_company_connections(
    company_id: str,
    connection_type: str = "all",
    sort_by: str = "volume",
    limit: int = 20,
    ctx: Context = None,
) -> dict:
    """Get vendors/customers for a specific company from the relationships table.

    Queries the MySQL relationships table where the company is the source entity,
    returning enriched golden record data for each connected entity.

    Args:
        company_id: The company's ID (e.g., "1" for Acme Corp).
        connection_type: Filter by type — 'vendor', 'customer', or 'all' (default 'all').
        sort_by: Sort results by 'volume', 'count', or 'name' (default 'volume').
        limit: Maximum results to return (default 20).

    Returns:
        Dict with 'connections' list, 'total' count, and summary stats.
    """
    app: AppContext = ctx.request_context.lifespan_context

    rows = app.mysql.get_relationships(
        company_id=company_id,
        connection_type=connection_type,
        sort_by=sort_by,
        limit=limit,
    )

    connections = []
    total_volume = 0.0
    total_txns = 0
    for r in rows:
        vol = float(r.get("transaction_volume") or 0)
        txn = int(r.get("transaction_count") or 0)
        total_volume += vol
        total_txns += txn

        conn_type = r.get("connection_type", "vendor")
        # For vendors, the other entity is target; for customers, it's source
        other_id = r.get("target_entity_id", "") if conn_type == "vendor" else r.get("source_entity_id", "")
        connections.append({
            "golden_record_id": other_id,
            "canonical_name": r.get("canonical_name", ""),
            "state": r.get("state", ""),
            "city": r.get("city", ""),
            "naics_code": r.get("naics_code", ""),
            "confidence": float(r.get("confidence", 0)),
            "entity_type": r.get("entity_type", ""),
            "source_count": int(r.get("source_count", 1)),
            "transaction_volume": vol,
            "transaction_count": txn,
            "connection_type": conn_type,
        })

    return {
        "connections": connections,
        "total": len(connections),
        "company_id": company_id,
        "connection_type": connection_type,
        "sort_by": sort_by,
        "summary": {
            "total_volume": round(total_volume, 2),
            "total_transactions": total_txns,
            "avg_volume_per_connection": round(total_volume / len(connections), 2) if connections else 0,
        },
    }


# ── Tool 18: get_merge_history ───────────────────────────────

@mcp.tool()
async def get_merge_history(
    entity_id: str,
    limit: int = 50,
    ctx: Context = None,
) -> dict:
    """Retrieve the merge/resolution audit trail for a golden record.

    Shows all resolution decisions that affected this entity, including
    merges into it, merges from it, and review submissions.

    Args:
        entity_id: Golden record ID.
        limit: Maximum audit records to return (default 50).

    Returns:
        Dict with 'audit_records' list and summary counts.
    """
    app: AppContext = ctx.request_context.lifespan_context

    records = app.mysql.get_audit_trail(entity_id, limit=limit)

    # Summarize
    merge_count = sum(1 for r in records if r.get("decision") == "MERGE")
    review_count = sum(1 for r in records if r.get("decision") == "REVIEW")
    new_entity_count = sum(1 for r in records if r.get("decision") == "NEW_ENTITY")

    return {
        "entity_id": entity_id,
        "audit_records": records,
        "total_records": len(records),
        "summary": {
            "merges": merge_count,
            "reviews": review_count,
            "new_entities": new_entity_count,
        },
    }
