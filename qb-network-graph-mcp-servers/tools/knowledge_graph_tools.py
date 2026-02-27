"""
Knowledge graph tools — extracted from KnowledgeGraphServer.

4 tools: query_ontology, check_shared_context, write_entity_triples, write_merge_redirect
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
    if not app.graphdb.available:
        return _fallback_ontology(code_a, code_b)

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
    path_a = app.graphdb.query_naics_hierarchy(code_a)
    path_b = app.graphdb.query_naics_hierarchy(code_b)
    lca = app.graphdb.query_lowest_common_ancestor(code_a, code_b)
    cross_links = app.graphdb.query_cross_taxonomy_links(code_a, code_b)

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


def _fallback_ontology(code_a: str, code_b: str) -> dict:
    """Fallback when GraphDB is unavailable — conservative string prefix matching."""
    if not code_a or not code_b:
        return {"related": False, "relationship_type": "UNRELATED",
                "semantic_distance": 1.0, "cross_taxonomy_links": [],
                "explanation": "Ontology unavailable, codes missing"}
    shared_prefix = 0
    for a, b in zip(code_a, code_b):
        if a == b:
            shared_prefix += 1
        else:
            break

    if shared_prefix >= 4:
        return {"related": True, "relationship_type": "SIBLING",
                "semantic_distance": 0.2, "cross_taxonomy_links": [],
                "explanation": f"Prefix match ({shared_prefix} digits) — likely related"}
    elif shared_prefix >= 2:
        return {"related": True, "relationship_type": "ANCESTOR",
                "semantic_distance": 0.5, "cross_taxonomy_links": [],
                "explanation": f"Same sector ({code_a[:2]}) — possibly related"}
    else:
        return {"related": False, "relationship_type": "UNRELATED",
                "semantic_distance": 0.8, "cross_taxonomy_links": [],
                "explanation": "Different sectors, no ontology available"}


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

    if not app.graphdb.available:
        return {"shared_neighbors": [], "industry_coherence": 0.0,
                "supporting_evidence": "GraphDB unavailable"}

    a_neighbors = app.graphdb.query_shared_neighbors(entity_a_id)
    a_neighbor_ids = {n.get("neighbor", "").split("/")[-1] for n in a_neighbors}

    shared = []
    for cp_id in known_counterparties:
        if cp_id in a_neighbor_ids:
            for n in a_neighbors:
                if n.get("neighbor", "").split("/")[-1] == cp_id:
                    shared.append({
                        "entity_id": cp_id,
                        "name": n.get("name", ""),
                        "industry_naics": n.get("naics", ""),
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


# ── Tool 6: write_entity_triples ────────────────────────────

@mcp.tool()
async def write_entity_triples(
    entity_id: str,
    attrs: dict,
    ctx: Context = None,
) -> dict:
    """Write A-Box triples for entity lifecycle events (create/update).

    Creates or updates an entity's RDF triples in the knowledge graph,
    including NAICS classification, geo location, name variants, and identity.

    Args:
        entity_id: Golden record ID.
        attrs: Dict with canonical_name, entity_type, confidence, naics_codes, name_variants, etc.

    Returns:
        Dict with 'success' bool, 'triples_written' count, 'fallback_to_changelog' flag.
    """
    app: AppContext = ctx.request_context.lifespan_context

    if not app.graphdb.available:
        logger.warning(f"GraphDB unavailable — falling back to changelog for {entity_id}")
        return {"success": False, "triples_written": 0, "fallback_to_changelog": True}

    count = app.graphdb.create_entity_triples(entity_id, attrs)
    return {
        "success": count > 0,
        "triples_written": count,
        "fallback_to_changelog": False,
    }


# ── Tool 7: write_merge_redirect ────────────────────────────

@mcp.tool()
async def write_merge_redirect(
    survivor_id: str,
    absorbed_id: str,
    survivor_updates: dict,
    ctx: Context = None,
) -> dict:
    """Handle KG updates for golden-to-golden merges.

    Migrates relationship triples from absorbed to survivor, updates survivor
    attributes, deletes absorbed attributes, then creates owl:sameAs redirect.
    CRITICAL: owl:sameAs must be written LAST to avoid premature inheritance.

    Args:
        survivor_id: Golden record ID of the surviving entity.
        absorbed_id: Golden record ID of the absorbed (merged) entity.
        survivor_updates: Dict with name_variants and unspsc_codes to add to survivor.

    Returns:
        Dict with 'success', 'triples_migrated', 'triples_created', 'redirect_created'.
    """
    app: AppContext = ctx.request_context.lifespan_context

    if not app.graphdb.available:
        logger.warning(f"GraphDB unavailable — merge redirect deferred for {absorbed_id} -> {survivor_id}")
        return {"success": False, "fallback_to_changelog": True,
                "triples_migrated": 0, "redirect_created": False}

    result = app.graphdb.write_merge_redirect(survivor_id, absorbed_id, survivor_updates)
    result["success"] = result.get("redirect_created", False)
    result["fallback_to_changelog"] = False
    return result
