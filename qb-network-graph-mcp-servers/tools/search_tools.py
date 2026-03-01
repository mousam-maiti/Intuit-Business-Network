"""
Conversational search tools — 6 NEW tools for AI chat / agent discovery.

13. search_entities       — semantic/hybrid search over golden records (Neo4j + Milvus)
14. describe_entity       — full profile: Neo4j + neighbors
15. query_network         — multi-hop graph traversal (Neo4j)
16. aggregate_stats       — GROUP BY queries (Neo4j)
17. search_by_relationship — find entities by relationship type (Neo4j)
18. get_merge_history     — audit trail from Neo4j AuditEntry nodes
"""
from __future__ import annotations
import json
import logging
import time

from mcp.server.fastmcp import Context

from app import mcp, AppContext
from clients.redis_client import RedisClient

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
    """Search golden records using hybrid search: Neo4j name match + Milvus vector search.

    Performs a 3-tier Neo4j name lookup (exact → CONTAINS → FULLTEXT) first to catch
    precise name matches, then augments with Milvus vector similarity results.

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

    # ── Phase 1: Neo4j name search (exact → CONTAINS → FULLTEXT) ──
    neo4j_hits = app.neo4j.search_by_name(
        query=query,
        state_filter=state_filter,
        city_filter=city_filter,
        naics_filter=naics_filter,
        min_confidence=min_confidence,
        limit=limit,
    )
    for hit in neo4j_hits:
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

                gr_data = app.neo4j.get_golden_record(gr_id)
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
            logger.warning(f"Milvus search failed, using Neo4j results only: {e}")

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

    Reads from Neo4j (primary store) and enriches with graph neighbors.

    Args:
        entity_id: Golden record ID.

    Returns:
        Dict with 'entity' profile, 'neighbors' list.
    """
    app: AppContext = ctx.request_context.lifespan_context

    gr_data = app.neo4j.get_golden_record(entity_id)
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
            "top_keywords": gr_data.get("commodity_keywords") or persona.get("commodity", {}).get("top_keywords", []),
            "service_categories": gr_data.get("service_categories") or persona.get("commodity", {}).get("service_categories", []),
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

    # Neo4j neighbors (directed graph) — already has all fields on Entity nodes
    neighbors = []
    if app.neo4j.available:
        raw_neighbors = app.neo4j.get_entity_neighbors(entity_id, direction="both")
        for n in raw_neighbors:
            neighbors.append({
                "entity_id": n.get("id", ""),
                "name": n.get("name", ""),
                "rel_type": n.get("rel_type", ""),
                "volume": float(n.get("volume") or 0),
            })

    return {
        "entity": profile,
        "neighbors": neighbors,
        "neighbor_count": len(neighbors),
        "neo4j_available": app.neo4j.available,
    }


# ── Tool 15: query_network ──────────────────────────────────

@mcp.tool()
async def query_network(
    entity_id: str,
    depth: int = 1,
    direction: str = "both",
    ctx: Context = None,
) -> dict:
    """Multi-hop graph traversal via transaction edges.

    Explores the transaction network around an entity up to the specified depth.

    Args:
        entity_id: Starting golden record ID.
        depth: How many hops to traverse (1-3, default 1).
        direction: 'outgoing', 'incoming', or 'both' (default 'both').

    Returns:
        Dict with 'nodes' and 'edges' for the subgraph, plus 'depth_reached'.
    """
    app: AppContext = ctx.request_context.lifespan_context

    depth = max(1, min(3, depth))  # Clamp to 1-3

    if not app.neo4j.available:
        return {"nodes": [], "edges": [], "depth_reached": 0,
                "error": "Neo4j unavailable — cannot traverse network"}

    return _query_network_neo4j(app, entity_id, depth, direction)


def _query_network_neo4j(
    app: "AppContext", entity_id: str, depth: int, direction: str,
) -> dict:
    """Neo4j-backed query_network with direction-aware traversal."""
    neo4j_dir = direction if direction in ("outgoing", "incoming", "both") else "both"

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

            neighbors = app.neo4j.get_entity_neighbors(eid, direction=neo4j_dir)

            # Neo4j has all fields on Entity nodes — no MySQL enrichment needed
            gr_data = app.neo4j.get_golden_record(eid)
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

            for n in neighbors:
                neighbor_id = n.get("id", "")
                if not neighbor_id:
                    continue

                edges.append({
                    "source": eid,
                    "target": neighbor_id,
                    "relationship": n.get("rel_type", "BUYS_FROM"),
                    "direction": "outgoing" if n.get("is_outgoing") else "incoming",
                    "volume": float(n.get("volume") or 0),
                    "target_name": n.get("name", ""),
                })

                if neighbor_id not in visited:
                    next_frontier.add(neighbor_id)

        frontier = next_frontier
        if not frontier:
            break

    for eid in frontier:
        if eid not in visited:
            gr_data = app.neo4j.get_golden_record(eid)
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
        "source": "neo4j",
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

    Runs GROUP BY queries on Neo4j Entity nodes to produce counts
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

    groups = app.neo4j.aggregate_golden_records(
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
    relationship_type: str = "BUYS_FROM",
    company_id: str = None,
    ctx: Context = None,
) -> dict:
    """Find entities connected to a given entity via a specific relationship.

    Queries Neo4j for entities related through the specified directed relationship type.

    Args:
        entity_id: Golden record ID to search from.
        relationship_type: Relationship to follow (default 'BUYS_FROM').
            Supported: BUYS_FROM, SELLS_TO.
        company_id: Optional company ID (unused, kept for API compatibility).

    Returns:
        Dict with 'related_entities' list and 'relationship_type'.
    """
    app: AppContext = ctx.request_context.lifespan_context

    if not app.neo4j.available:
        return {"error": "Neo4j unavailable — cannot query relationships",
                "related_entities": [], "count": 0}

    allowed = {"BUYS_FROM", "SELLS_TO"}
    if relationship_type not in allowed:
        return {"error": f"Unsupported relationship_type: {relationship_type}. "
                         f"Allowed: {sorted(allowed)}"}

    neighbors = app.neo4j.get_entity_neighbors(
        entity_id, direction="outgoing", rel_type=relationship_type)

    related = []
    for n in neighbors:
        neighbor_id = n.get("id", "")
        if not neighbor_id:
            continue
        related.append({
            "entity_id": neighbor_id,
            "name": n.get("name", ""),
            "canonical_name": n.get("name", ""),
            "rel_type": n.get("rel_type", ""),
            "volume": float(n.get("volume") or 0),
        })

    return {
        "related_entities": related,
        "count": len(related),
        "source_entity": entity_id,
        "relationship_type": relationship_type,
        "source": "neo4j",
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
    """Get vendors/customers for a specific company from Neo4j.

    Queries Neo4j Entity relationships where the company is the source entity,
    returning all fields directly from Entity nodes.

    Args:
        company_id: The company's ID (e.g., "1" for Acme Corp).
        connection_type: Filter by type — 'vendor', 'customer', or 'all' (default 'all').
        sort_by: Sort results by 'volume', 'count', or 'name' (default 'volume').
        limit: Maximum results to return (default 20).

    Returns:
        Dict with 'connections' list, 'total' count, and summary stats.
    """
    app: AppContext = ctx.request_context.lifespan_context

    rows = app.neo4j.get_relationships(
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

    Reads from Neo4j AuditEntry nodes. Shows all resolution decisions
    that affected this entity, including merges into it, merges from it,
    and review submissions.

    Args:
        entity_id: Golden record ID.
        limit: Maximum audit records to return (default 50).

    Returns:
        Dict with 'audit_records' list and summary counts.
    """
    app: AppContext = ctx.request_context.lifespan_context

    records = app.neo4j.get_audit_trail(entity_id, limit=limit)

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


# ── Tool 20: traverse_supply_chain ───────────────────────────

@mcp.tool()
async def traverse_supply_chain(
    start_entity_id: str,
    hops: list[str],
    max_per_hop: int = 5,
    min_volume: float = 0,
    ctx: Context = None,
) -> dict:
    """Directed multi-hop supply chain traversal via Neo4j.

    Follows vendor/client relationship chains across the business network.
    Each hop specifies the direction: 'vendor' (BUYS_FROM) or 'client' (SELLS_TO).

    Examples:
      ["vendor"] — direct vendors
      ["vendor", "client"] — vendor's other clients
      ["vendor", "client", "vendor"] — full supply chain loop (3-hop)

    Args:
        start_entity_id: Starting entity (company or golden record ID).
        hops: List of directions for each hop, e.g. ["vendor", "client", "vendor"].
        max_per_hop: Maximum entities to follow per hop (default 5, sorted by volume).
        min_volume: Minimum transaction volume to include in traversal.

    Returns:
        Dict with paths, nodes, edges, and supply chain insights.
    """
    app: AppContext = ctx.request_context.lifespan_context
    start = time.time()

    # Validate hops
    valid_hops = {"vendor", "client", "customer"}
    for h in hops:
        if h not in valid_hops:
            return {"error": f"Invalid hop direction: '{h}'. Use 'vendor' or 'client'."}
    if len(hops) > 5:
        return {"error": "Maximum 5 hops supported."}

    if not app.neo4j.available:
        return {"error": "Neo4j unavailable — cannot traverse supply chain",
                "paths": [], "total_paths": 0}

    # Check Redis cache
    cache_key = RedisClient.traverse_key(start_entity_id, hops)
    cached = await app.redis.get_cached(cache_key)
    if cached:
        cached["from_cache"] = True
        cached["duration_ms"] = int((time.time() - start) * 1000)
        return cached

    # Neo4j directed traversal
    raw_paths = app.neo4j.traverse_supply_chain(
        start_id=start_entity_id,
        hops=hops,
        max_per_hop=max_per_hop,
        min_volume=min_volume,
    )

    paths = []
    for rp in raw_paths:
        chain = []
        for i, node in enumerate(rp.get("chain", [])):
            chain.append({
                "id": node.get("id", ""),
                "name": node.get("name", ""),
                "hop": i,
                "type": node.get("type", ""),
            })

        edges = []
        for j, edge in enumerate(rp.get("edges", [])):
            edges.append({
                "from": chain[j]["id"] if j < len(chain) else "",
                "to": chain[j + 1]["id"] if j + 1 < len(chain) else "",
                "type": edge.get("type", ""),
                "volume": float(edge.get("volume") or 0),
            })

        paths.append({
            "chain": chain,
            "edges": edges,
            "total_volume": float(rp.get("total_volume", 0)),
        })

    # Build unique node set across all paths
    all_nodes = {}
    for p in paths:
        for node in p.get("chain", []):
            nid = node.get("id", "")
            if nid and nid not in all_nodes:
                all_nodes[nid] = node

    # Compute insights
    insights = _compute_insights(paths, start_entity_id)

    result = {
        "paths": paths,
        "total_paths": len(paths),
        "nodes": list(all_nodes.values()),
        "insights": insights,
        "depth": len(hops),
        "duration_ms": int((time.time() - start) * 1000),
        "from_cache": False,
    }

    # Cache result
    await app.redis.set_cached(cache_key, result)

    return result


def _compute_insights(paths: list[dict], start_id: str) -> dict:
    """Compute supply chain insights from traversal results."""
    if not paths:
        return {
            "shared_entities": [],
            "circular_paths": [],
            "concentration_risk": 0.0,
        }

    # Shared entities: appear at multiple hops across paths
    entity_hops: dict[str, set[int]] = {}
    for p in paths:
        for node in p.get("chain", []):
            nid = node.get("id", "")
            hop = node.get("hop", 0)
            if nid:
                entity_hops.setdefault(nid, set()).add(hop)
    shared = [
        {"id": eid, "hops": sorted(h)}
        for eid, h in entity_hops.items()
        if len(h) > 1 and eid != start_id
    ]

    # Circular paths: paths that loop back to start
    circular = [
        i for i, p in enumerate(paths)
        if p.get("chain") and p["chain"][-1].get("id") == start_id
    ]

    # Concentration risk: % of total volume through top entity at hop 1
    hop1_volumes: dict[str, float] = {}
    for p in paths:
        if len(p.get("edges", [])) >= 1:
            edge = p["edges"][0]
            target = edge.get("to", "")
            hop1_volumes[target] = hop1_volumes.get(target, 0) + edge.get("volume", 0)
    total_vol = sum(hop1_volumes.values())
    max_vol = max(hop1_volumes.values()) if hop1_volumes else 0
    concentration = round(max_vol / total_vol, 3) if total_vol > 0 else 0.0

    return {
        "shared_entities": shared,
        "circular_paths": circular,
        "concentration_risk": concentration,
    }
