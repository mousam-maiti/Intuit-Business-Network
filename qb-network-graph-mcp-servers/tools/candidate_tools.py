"""
Candidate evaluation tools — extracted from CandidateEvaluator.

3 tools: find_candidates, compare_fields, semantic_similarity
"""
from __future__ import annotations
import json
import logging
import time

from mcp.server.fastmcp import Context

from app import mcp, AppContext
from models.persona import ClassifiedPersona
from models.resolution import ComparisonResult, SimilarityResult
from utils.bucket_keys import generate_bucket_keys
from utils import scoring

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────

def _parse_list(val) -> list[str]:
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return [val] if val else []
    return val if isinstance(val, list) else []


def _parse_persona(val) -> dict:
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return {}
    return val if isinstance(val, dict) else {}


def _to_classified_persona(data: dict) -> ClassifiedPersona:
    if isinstance(data, ClassifiedPersona):
        return data
    try:
        return ClassifiedPersona.model_validate(data)
    except Exception:
        return ClassifiedPersona()


def _persona_to_texts(persona: ClassifiedPersona) -> dict[str, str]:
    parts = {}

    name_parts = [persona.identity.normalized_name]
    if persona.identity.legal_suffix:
        name_parts.append(persona.identity.legal_suffix)
    parts["name"] = " ".join(name_parts)

    ind_parts = []
    if persona.industry.naics_code:
        ind_parts.append(f"NAICS {persona.industry.naics_code}")
    if persona.industry.commodity_keywords:
        ind_parts.extend(persona.industry.commodity_keywords)
    parts["industry"] = " ".join(ind_parts) if ind_parts else ""

    if persona.commodity.top_keywords:
        parts["commodities"] = ", ".join(persona.commodity.top_keywords)
    else:
        parts["commodities"] = ""

    loc_parts = []
    if persona.location.city_norm:
        loc_parts.append(persona.location.city_norm)
    if persona.location.state:
        loc_parts.append(persona.location.state)
    if persona.location.zip5:
        loc_parts.append(persona.location.zip5)
    parts["location"] = ", ".join(loc_parts) if loc_parts else ""

    return parts


# ── Tool 1: find_candidates ─────────────────────────────────

@mcp.tool()
async def find_candidates(
    orphan_persona: dict,
    max_candidates: int = 20,
    ctx: Context = None,
) -> dict:
    """Retrieve candidate golden records by persona-dimension bucket keys.

    Generates bucket keys from the orphan persona and queries MySQL indexed
    columns to find matching golden records. Candidates are sorted by the
    number of shared bucket keys (more overlap = stronger signal).

    Args:
        orphan_persona: Classified persona dict with identity, industry, location, commodity, behavioral dimensions.
        max_candidates: Maximum number of candidates to return (default 20).

    Returns:
        Dict with 'candidates' list, 'bucket_stats', and 'duration_ms'.
    """
    app: AppContext = ctx.request_context.lifespan_context
    start = time.time()

    persona = _to_classified_persona(orphan_persona)
    keys = generate_bucket_keys(persona, max_commodity_kw=app.config.buckets.max_commodity_keywords)

    candidate_buckets: dict[str, list[str]] = {}
    total_before_dedup = 0
    buckets_used = []

    for bk in keys:
        members = app.mysql.find_by_bucket_key(bk)
        buckets_used.append({"key": bk, "candidate_count": len(members)})
        total_before_dedup += len(members)
        for gr_id in members:
            candidate_buckets.setdefault(gr_id, []).append(bk)

    sorted_candidates = sorted(
        candidate_buckets.items(),
        key=lambda x: len(x[1]),
        reverse=True,
    )[:max_candidates]

    candidates = []
    for gr_id, matched_buckets in sorted_candidates:
        gr_data = app.mysql.get_golden_record(gr_id)
        if not gr_data:
            continue
        candidates.append({
            "golden_record_id": gr_id,
            "canonical_name": gr_data.get("canonical_name", ""),
            "name_variants": _parse_list(gr_data.get("name_variants", [])),
            "persona": _parse_persona(gr_data.get("persona", {})),
            "source_count": int(gr_data.get("source_count", 1)),
            "confidence": float(gr_data.get("confidence", 0.5)),
            "matched_via_buckets": matched_buckets,
        })

    elapsed = int((time.time() - start) * 1000)
    return {
        "candidates": candidates,
        "bucket_stats": {
            "total_buckets_checked": len(keys),
            "total_candidates_before_dedup": total_before_dedup,
            "total_candidates_after_dedup": len(candidate_buckets),
            "buckets_used": buckets_used,
        },
        "duration_ms": elapsed,
    }


# ── Tool 2: compare_fields ──────────────────────────────────

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
    persona = _to_classified_persona(orphan_persona)
    cand_persona = _to_classified_persona(candidate.get("persona", {}))
    cand_variants = candidate.get("name_variants", [])

    # Hard disqualifiers
    o_ein = persona.identity.ein_clean
    c_ein = cand_persona.identity.ein_clean
    if o_ein and c_ein and o_ein != c_ein:
        return ComparisonResult(
            disqualified=True,
            disqualification_reason="Different EIN",
        ).model_dump()

    o_state = persona.location.state
    c_state = cand_persona.location.state
    if o_state and c_state and o_state.upper() != c_state.upper():
        return ComparisonResult(
            disqualified=True,
            disqualification_reason="Different state",
        ).model_dump()

    # Score each dimension
    identity = scoring.score_identity(persona, cand_persona, cand_variants)

    ontology_score = None
    if persona.industry.naics_code and cand_persona.industry.naics_code:
        o_sec = persona.industry.naics_code[:2]
        c_sec = cand_persona.industry.naics_code[:2]
        if o_sec != c_sec and app.graphdb.available:
            from tools.knowledge_graph_tools import _query_ontology_internal
            ontology_result = _query_ontology_internal(
                app, "INDUSTRY_RELATION",
                persona.industry.naics_code,
                cand_persona.industry.naics_code,
            )
            if ontology_result.get("cross_taxonomy_links"):
                ontology_score = 0.40
            elif ontology_result.get("semantic_distance", 1.0) < 0.5:
                ontology_score = 0.30
            else:
                ontology_score = 0.0

    industry = scoring.score_industry(persona, cand_persona, ontology_score)
    location = scoring.score_location(persona, cand_persona)
    commodity = scoring.score_commodity(persona, cand_persona)
    behavioral = scoring.score_behavioral(persona, cand_persona)

    dimensions = {
        "identity": identity, "industry": industry,
        "location": location, "commodity": commodity,
        "behavioral": behavioral,
    }
    base_weights = app.config.weights.as_dict()
    composite, weights_used, sparsity_adj = scoring.compute_composite(dimensions, base_weights)

    return ComparisonResult(
        identity=identity, industry=industry, location=location,
        commodity=commodity, behavioral=behavioral,
        composite=composite, weights_used=weights_used,
        sparsity_adjusted=sparsity_adj, disqualified=False,
    ).model_dump()


# ── Tool 3: semantic_similarity ──────────────────────────────

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
    persona = _to_classified_persona(orphan_persona)
    cand_persona = _to_classified_persona(candidate.get("persona", {}))

    orphan_texts = _persona_to_texts(persona)
    candidate_texts = _persona_to_texts(cand_persona)

    weights = app.config.weights.as_dict()
    result = app.embedding.compute_similarity(orphan_texts, candidate_texts, weights)

    return SimilarityResult(
        name_similarity=result.get("name_similarity", 0.0),
        industry_similarity=result.get("industry_similarity", 0.0),
        commodity_similarity=result.get("commodity_similarity", 0.0),
        location_similarity=result.get("location_similarity", 0.0),
        composite_similarity=result.get("composite_similarity", 0.0),
        model_used=result.get("model_used", ""),
        inference_ms=result.get("inference_ms", 0),
    ).model_dump()
