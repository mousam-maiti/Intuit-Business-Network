"""
Knowledge graph tools — T-Box ontology queries + graph analytics via Neo4j.

Tools: query_ontology, check_shared_context, batch_industry_filter,
       find_shortest_path, find_common_neighbors, detect_cluster, assess_risk_impact

All entity reads come from Neo4j (primary store). MySQL fallbacks removed.
"""
from __future__ import annotations
import logging
import time

from mcp.server.fastmcp import Context

from app import mcp, AppContext

logger = logging.getLogger(__name__)


# ── Internal helpers (used by other tool modules) ────────────

def _query_ontology_internal(app: AppContext, query_type: str, code_a: str, code_b: str) -> dict:
    """Internal ontology query — called by compare_fields for cross-taxonomy links."""
    if query_type == "INDUSTRY_RELATION":
        return _query_industry_relation(app, code_a, code_b)
    elif query_type == "COMMODITY_RELATION":
        return _query_commodity_relation(code_a, code_b)
    elif query_type == "GEO_CONTAINMENT":
        return _query_geo_containment(code_a, code_b)
    else:
        return {"error": f"Unknown query_type: {query_type}"}


def _query_industry_relation(app: AppContext, code_a: str, code_b: str) -> dict:
    start = time.time()

    # Pure-Python NAICS hierarchy (no DB needed)
    from clients.neo4j_client import Neo4jClient
    path_a = Neo4jClient.query_naics_hierarchy(code_a)
    path_b = Neo4jClient.query_naics_hierarchy(code_b)
    lca = Neo4jClient.query_lowest_common_ancestor(code_a, code_b)

    # Cross-taxonomy links: Neo4j if available, else static fallback
    cross_links = app.neo4j.query_cross_taxonomy_links(code_a, code_b)

    if code_a == code_b:
        distance, rel_type = 0.0, "SAME"
    elif lca and len(lca) >= 3:
        distance, rel_type = 0.2, "SIBLING"
    elif lca and len(lca) >= 2:
        distance, rel_type = 0.4, "ANCESTOR"
    elif cross_links:
        distance, rel_type = 0.35, "CROSS_TAXONOMY_LINK"
    else:
        distance, rel_type = 0.8, "UNRELATED"

    explanation = _build_industry_explanation(code_a, code_b, path_a, path_b, lca, cross_links, rel_type)

    return {
        "related": distance < 0.7,
        "relationship_type": rel_type,
        "path_a": path_a,
        "path_b": path_b,
        "lowest_common_ancestor": lca,
        "cross_taxonomy_links": cross_links,
        "semantic_distance": round(distance, 3),
        "explanation": explanation,
        "duration_ms": int((time.time() - start) * 1000),
    }


def _build_industry_explanation(code_a, code_b, path_a, path_b, lca, cross_links, rel_type) -> str:
    if rel_type == "SAME":
        return f"Same NAICS code: {code_a}"
    if rel_type == "SIBLING":
        return (f"NAICS {code_a} and {code_b} share common ancestor {lca}. "
                "Same subsector — closely related industries.")
    if rel_type == "CROSS_TAXONOMY_LINK":
        link_desc = ", ".join(l.get("label", l.get("code", "?")) for l in cross_links)
        return (f"Different NAICS sectors ({code_a[:2]} vs {code_b[:2]}) "
                f"but linked via shared commodity taxonomy: {link_desc}.")
    return f"NAICS {code_a} and {code_b} appear unrelated (no common ancestor or cross-taxonomy links)."


def _query_commodity_relation(code_a: str, code_b: str) -> dict:
    start = time.time()
    prefix_match = min(len(code_a), len(code_b))
    shared = 0
    for i in range(prefix_match):
        if code_a[i] == code_b[i]:
            shared += 1
        else:
            break
    distance = 1.0 - (shared / max(len(code_a), len(code_b), 1))
    return {
        "related": distance < 0.5,
        "relationship_type": "SAME" if distance == 0 else "SIBLING" if distance < 0.3 else "UNRELATED",
        "semantic_distance": round(distance, 3),
        "duration_ms": int((time.time() - start) * 1000),
    }


def _query_geo_containment(geo_a: str, geo_b: str) -> dict:
    start = time.time()
    return {
        "related": geo_a.lower() == geo_b.lower(),
        "relationship_type": "SAME" if geo_a.lower() == geo_b.lower() else "UNRELATED",
        "duration_ms": int((time.time() - start) * 1000),
    }


# ── Tool 4: query_ontology ──────────────────────────────────

@mcp.tool()
async def query_ontology(
    query_type: str,
    code_a: str = "",
    code_b: str = "",
    ctx: Context = None,
) -> dict:
    """Query T-Box ontology for semantic relationships between NAICS/commodity/geo codes.

    Used to determine if seemingly different industry codes are actually related
    (e.g., plumbing wholesaler and plumbing contractor share commodity taxonomy).

    Args:
        query_type: Type of query — INDUSTRY_RELATION, COMMODITY_RELATION, or GEO_CONTAINMENT.
        code_a: First NAICS/commodity/geo code.
        code_b: Second NAICS/commodity/geo code.

    Returns:
        Dict with 'related' bool, 'relationship_type', 'semantic_distance' (0=same, 1=unrelated),
        'cross_taxonomy_links', and 'explanation'.
    """
    app: AppContext = ctx.request_context.lifespan_context
    return _query_ontology_internal(app, query_type, code_a, code_b)


# ── Tool 5: check_shared_context ────────────────────────────

@mcp.tool()
async def check_shared_context(
    entity_a_id: str,
    known_counterparties: list[str],
    ctx: Context = None,
) -> dict:
    """Ontology-aware shared neighbor analysis.

    Checks if a candidate entity and an orphan's known counterparties share
    transaction partners, and whether they form a coherent industry cluster.

    Args:
        entity_a_id: Golden record ID of the candidate entity.
        known_counterparties: List of golden record IDs that the orphan transacts with.

    Returns:
        Dict with 'shared_neighbors' list, 'industry_coherence' float, and 'supporting_evidence'.
    """
    app: AppContext = ctx.request_context.lifespan_context

    if not app.neo4j.available:
        return {"shared_neighbors": [], "industry_coherence": 0.0,
                "supporting_evidence": "Neo4j unavailable — shared neighbor analysis disabled"}

    a_neighbors = app.neo4j.get_entity_neighbors(entity_a_id, direction="both")
    a_neighbor_ids = {n.get("id", "") for n in a_neighbors}

    shared = []
    for cp_id in known_counterparties:
        if cp_id in a_neighbor_ids:
            gr_data = app.neo4j.get_golden_record(cp_id)
            shared.append({
                "entity_id": cp_id,
                "name": gr_data.get("canonical_name", "") if gr_data else "",
                "industry_naics": gr_data.get("naics_code", "") if gr_data else "",
            })

    coherence = 0.0
    if shared:
        naics_codes = [s.get("industry_naics", "") for s in shared if s.get("industry_naics")]
        if len(naics_codes) >= 2:
            sectors = set(c[:2] for c in naics_codes if len(c) >= 2)
            coherence = 1.0 / max(len(sectors), 1)
        elif len(naics_codes) == 1:
            coherence = 0.5

    evidence = (
        f"Found {len(shared)} shared transaction partners. "
        f"Industry coherence: {coherence:.2f}."
    ) if shared else "No shared transaction partners found."

    return {
        "shared_neighbors": shared,
        "industry_coherence": round(coherence, 3),
        "supporting_evidence": evidence,
    }


# ── Tool 10: batch_industry_filter ──────────────────────────

@mcp.tool()
async def batch_industry_filter(
    reference_naics: str,
    candidates: list[dict],
    ctx: Context = None,
) -> dict:
    """Check which candidates are related to a reference NAICS code via ontology.

    Compares a reference NAICS code (e.g., lumber 423310) against multiple
    candidate NAICS codes in a single call. Much faster than calling
    query_ontology once per candidate.

    Args:
        reference_naics: The NAICS code representing the target industry (e.g., "423310" for lumber).
        candidates: List of dicts with at least 'naics_code' and 'name' fields.
            Example: [{"naics_code": "236220", "name": "Acme", "golden_record_id": "G-xxx"}]

    Returns:
        Dict with 'matches' (related candidates) and 'unmatched_count'.
    """
    app: AppContext = ctx.request_context.lifespan_context

    matches = []
    for c in candidates:
        code = c.get("naics_code") or ""
        if not code:
            continue
        # Check industry relation
        result = _query_ontology_internal(app, "INDUSTRY_RELATION", reference_naics, code)
        if result.get("related"):
            matches.append({**c, "relationship": result.get("relationship_type", ""), "explanation": result.get("explanation", "")})
            continue
        # Check commodity relation
        result = _query_ontology_internal(app, "COMMODITY_RELATION", reference_naics, code)
        if result.get("related"):
            matches.append({**c, "relationship": "COMMODITY_LINK", "explanation": f"Shared commodity taxonomy (distance {result.get('semantic_distance', '?')})"})
            continue
        # Check same 2-digit sector
        if len(reference_naics) >= 2 and len(code) >= 2 and reference_naics[:2] == code[:2]:
            matches.append({**c, "relationship": "SAME_SECTOR", "explanation": f"Same NAICS sector ({code[:2]})"})

    return {
        "reference_naics": reference_naics,
        "matches": matches,
        "match_count": len(matches),
        "unmatched_count": len(candidates) - len(matches),
        "total_candidates": len(candidates),
    }


# ── Tool 12: find_shortest_path ──────────────────────────────

@mcp.tool()
async def find_shortest_path(
    entity_a: str,
    entity_b: str,
    ctx: Context = None,
) -> dict:
    """Find the shortest connection path between any two entities in the network.

    Args:
        entity_a: Golden record ID of the first entity.
        entity_b: Golden record ID of the second entity.

    Returns:
        Dict with 'chain' (enriched nodes), 'edges', 'hops', and 'duration_ms'.
    """
    app: AppContext = ctx.request_context.lifespan_context
    start = time.time()

    if not app.neo4j.available:
        return {"chain": [], "edges": [], "hops": -1,
                "error": "Neo4j unavailable — cannot find shortest path",
                "duration_ms": int((time.time() - start) * 1000)}

    raw = app.neo4j.find_shortest_path(entity_a, entity_b)
    if raw:
        # Neo4j Entity nodes have all fields — no MySQL enrichment needed
        chain = []
        for node in raw.get("chain", []):
            chain.append({
                "id": node.get("id", ""),
                "name": node.get("name", ""),
                "type": node.get("type", ""),
            })
        return {
            "chain": chain,
            "edges": raw.get("edges", []),
            "hops": raw.get("hops", 0),
            "duration_ms": int((time.time() - start) * 1000),
        }
    return {
        "chain": [], "edges": [], "hops": -1,
        "message": "No path found between the two entities.",
        "duration_ms": int((time.time() - start) * 1000),
    }


# ── Tool 13: find_common_neighbors ────────────────────────────

@mcp.tool()
async def find_common_neighbors(
    entity_a_id: str,
    entity_b_id: str,
    limit: int = 20,
    ctx: Context = None,
) -> dict:
    """Find entities that are direct transaction partners of BOTH given entities.

    Args:
        entity_a_id: Golden record ID of the first entity.
        entity_b_id: Golden record ID of the second entity.
        limit: Maximum results to return (default 20).

    Returns:
        Dict with 'common_neighbors' list, 'count', and entity names.
    """
    app: AppContext = ctx.request_context.lifespan_context
    start = time.time()

    # Resolve names from Neo4j
    gr_a = app.neo4j.get_golden_record(entity_a_id)
    gr_b = app.neo4j.get_golden_record(entity_b_id)
    name_a = gr_a.get("canonical_name", entity_a_id) if gr_a else entity_a_id
    name_b = gr_b.get("canonical_name", entity_b_id) if gr_b else entity_b_id

    if not app.neo4j.available:
        return {"common_neighbors": [], "count": 0,
                "entity_a_name": name_a, "entity_b_name": name_b,
                "error": "Neo4j unavailable",
                "duration_ms": int((time.time() - start) * 1000)}

    raw = app.neo4j.find_common_neighbors(entity_a_id, entity_b_id, limit=limit)
    neighbors = []
    for r in raw:
        neighbors.append({
            "id": r.get("id", ""),
            "name": r.get("name", ""),
            "naics_code": r.get("naics_code", ""),
            "rel_to_a": r.get("rel_to_a", ""),
            "vol_a": float(r.get("vol_a") or 0),
            "rel_to_b": r.get("rel_to_b", ""),
            "vol_b": float(r.get("vol_b") or 0),
        })
    return {
        "common_neighbors": neighbors,
        "count": len(neighbors),
        "entity_a_name": name_a,
        "entity_b_name": name_b,
        "duration_ms": int((time.time() - start) * 1000),
    }


# ── Tool 14: detect_cluster ───────────────────────────────────

@mcp.tool()
async def detect_cluster(
    entity_id: str,
    max_size: int = 20,
    ctx: Context = None,
) -> dict:
    """Discover the business cluster (tightly connected subgroup) around an entity.

    Args:
        entity_id: Golden record ID of the center entity.
        max_size: Maximum cluster members to return (default 20).

    Returns:
        Dict with 'nodes', 'edges', 'density', 'center', 'member_count', and 'top_industries'.
    """
    app: AppContext = ctx.request_context.lifespan_context
    start = time.time()

    if not app.neo4j.available:
        return {"nodes": [], "edges": [], "density": 0.0, "center": entity_id,
                "member_count": 0, "top_industries": [],
                "error": "Neo4j unavailable",
                "duration_ms": int((time.time() - start) * 1000)}

    gr_center = app.neo4j.get_golden_record(entity_id)
    center_name = gr_center.get("canonical_name", entity_id) if gr_center else entity_id

    raw = app.neo4j.find_cluster(entity_id, max_size=max_size)
    if not raw:
        return {"nodes": [], "edges": [], "density": 0.0, "center": center_name,
                "member_count": 0, "top_industries": [],
                "duration_ms": int((time.time() - start) * 1000)}

    # Neo4j Entity nodes have all fields — use directly
    nodes = []
    for n in raw.get("nodes", []):
        nodes.append({
            "id": n.get("id", ""),
            "name": n.get("name", ""),
            "naics_code": n.get("naics_code", ""),
        })

    # Add center node
    nodes.insert(0, {
        "id": entity_id, "name": center_name,
        "naics_code": gr_center.get("naics_code", "") if gr_center else "",
        "state": gr_center.get("state", "") if gr_center else "",
        "is_center": True,
    })

    # Top industries
    naics_counts = {}
    for n in nodes:
        code = n.get("naics_code", "")
        if code:
            sector = code[:4] if len(code) >= 4 else code
            naics_counts[sector] = naics_counts.get(sector, 0) + 1
    top_industries = sorted(naics_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "nodes": nodes,
        "edges": raw.get("edges", []),
        "density": raw.get("density", 0.0),
        "center": center_name,
        "member_count": len(nodes),
        "top_industries": [{"naics": k, "count": v} for k, v in top_industries],
        "duration_ms": int((time.time() - start) * 1000),
    }


# ── Tool 15: assess_risk_impact ───────────────────────────────

@mcp.tool()
async def assess_risk_impact(
    entity_id: str,
    max_depth: int = 3,
    ctx: Context = None,
) -> dict:
    """Analyze downstream impact if an entity were to disappear from the network.

    Finds all entities that directly or transitively depend on (buy from) this entity.

    Args:
        entity_id: Golden record ID of the entity to assess.
        max_depth: Maximum depth to trace dependencies (default 3).

    Returns:
        Dict with 'affected_entities', 'total_volume_at_risk', 'depth_distribution',
        and 'concentration_warning'.
    """
    app: AppContext = ctx.request_context.lifespan_context
    start = time.time()

    if not app.neo4j.available:
        return {"affected_entities": [], "affected_count": 0,
                "total_volume_at_risk": 0, "depth_distribution": {},
                "error": "Neo4j unavailable",
                "duration_ms": int((time.time() - start) * 1000)}

    gr_target = app.neo4j.get_golden_record(entity_id)
    target_name = gr_target.get("canonical_name", entity_id) if gr_target else entity_id

    raw = app.neo4j.assess_impact(entity_id, max_depth=max_depth)
    if not raw:
        return {"target_entity": target_name,
                "affected_entities": [], "affected_count": 0,
                "total_volume_at_risk": 0, "depth_distribution": {},
                "duration_ms": int((time.time() - start) * 1000)}

    # Neo4j Entity nodes have all fields — use directly
    affected = []
    for a in raw.get("affected", []):
        affected.append({
            "id": a.get("id", ""),
            "name": a.get("name", ""),
            "depth": a.get("depth", 1),
            "volume_at_risk": float(a.get("volume_at_risk", 0)),
        })

    total_vol = raw.get("total_volume_at_risk", 0)
    depth_dist = raw.get("depth_distribution", {})
    concentration = _concentration_warning(affected, total_vol)

    return {
        "target_entity": target_name,
        "affected_entities": affected,
        "affected_count": len(affected),
        "total_volume_at_risk": total_vol,
        "depth_distribution": depth_dist,
        "concentration_warning": concentration,
        "duration_ms": int((time.time() - start) * 1000),
    }


def _concentration_warning(affected: list[dict], total_volume: float) -> str | None:
    """Generate a concentration warning if a single depth-1 entity holds >50% of volume."""
    if not affected or total_volume <= 0:
        return None
    depth_1 = [a for a in affected if a.get("depth") == 1]
    for a in depth_1:
        vol = a.get("volume_at_risk", 0)
        if vol > total_volume * 0.5:
            return (f"{a.get('name', a.get('id', '?'))} accounts for "
                    f"{vol / total_volume * 100:.0f}% of at-risk volume")
    return None
