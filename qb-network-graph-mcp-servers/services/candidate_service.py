"""
Candidate evaluation service — find_candidates, compare_fields, semantic_similarity.

Business logic extracted from candidate_tools.py.
"""
from __future__ import annotations

import json
import logging
import time

from interfaces.entity_repository import AbstractEntityRepository
from interfaces.embedding_provider import AbstractEmbeddingProvider
from models.persona import ClassifiedPersona
from models.resolution import ComparisonResult, SimilarityResult
from utils.bucket_keys import generate_bucket_keys
from utils import scoring

logger = logging.getLogger(__name__)


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


class CandidateService:
    """Candidate evaluation: find, compare, semantic similarity."""

    def __init__(
        self,
        entity_repo: AbstractEntityRepository,
        embedding: AbstractEmbeddingProvider,
        config,
    ):
        self._entity_repo = entity_repo
        self._embedding = embedding
        self._cfg = config

    def find_candidates(self, orphan_persona: dict, max_candidates: int = 20) -> dict:
        """Find candidates via identity anchors + vector search + bucket-key fallback."""
        start = time.time()
        persona = _to_classified_persona(orphan_persona)
        candidate_scores: dict[str, float] = {}   # gr_id → best score
        candidate_sources: dict[str, list[str]] = {}  # gr_id → how found

        # ── Layer 1: Deterministic identity anchors (EIN, phone, email) ──
        identity_keys = self._identity_bucket_keys(persona)
        for bk in identity_keys:
            members = self._entity_repo.find_by_bucket_key(bk)
            for gr_id in members:
                candidate_scores[gr_id] = 1.0
                candidate_sources.setdefault(gr_id, []).append(bk)

        # ── Layer 2: Scoped vector search ──
        vector_search_used = False
        embedding_text = self._build_embedding_text(persona)
        if embedding_text:
            query_vector = self._embedding.embed_text(embedding_text)
            if query_vector:
                state = persona.location.state or None
                vector_results = self._entity_repo.vector_search(
                    query_vector=query_vector,
                    state_filter=state,
                    top_k=max_candidates,
                )
                if vector_results:
                    vector_search_used = True
                    for vr in vector_results:
                        gr_id = vr["golden_record_id"]
                        vscore = vr["score"]
                        # Don't overwrite identity anchor 1.0 scores
                        if gr_id not in candidate_scores:
                            candidate_scores[gr_id] = vscore
                        candidate_sources.setdefault(gr_id, []).append(f"vector:{vscore:.3f}")

        # ── Layer 3: Bucket-key fallback (if vector search unavailable) ──
        if not vector_search_used:
            keys = generate_bucket_keys(persona, max_commodity_kw=self._cfg.buckets.max_commodity_keywords)
            for bk in keys:
                if bk in identity_keys:
                    continue  # already checked in Layer 1
                members = self._entity_repo.find_by_bucket_key(bk)
                for gr_id in members:
                    if gr_id not in candidate_scores:
                        candidate_scores[gr_id] = 0.5  # neutral score for bucket matches
                    candidate_sources.setdefault(gr_id, []).append(bk)

        # ── Merge & rank ──
        sorted_candidates = sorted(
            candidate_scores.items(), key=lambda x: x[1], reverse=True,
        )[:max_candidates]

        candidates = []
        for gr_id, score in sorted_candidates:
            gr_data = self._entity_repo.get(gr_id)
            if not gr_data:
                continue
            candidates.append({
                "golden_record_id": gr_id,
                "canonical_name": gr_data.get("canonical_name", ""),
                "name_variants": _parse_list(gr_data.get("name_variants", [])),
                "persona": _parse_persona(gr_data.get("persona", {})),
                "source_count": int(gr_data.get("source_count", 1)),
                "confidence": float(gr_data.get("confidence", 0.5)),
                "matched_via_buckets": candidate_sources.get(gr_id, []),
            })

        elapsed = int((time.time() - start) * 1000)
        return {
            "candidates": candidates,
            "bucket_stats": {
                "identity_keys_checked": len(identity_keys),
                "vector_search_used": vector_search_used,
                "total_candidates": len(candidate_scores),
            },
            "duration_ms": elapsed,
        }

    def _identity_bucket_keys(self, persona: ClassifiedPersona) -> list[str]:
        """Generate only deterministic identity bucket keys (EIN, phone, email)."""
        keys = []
        if persona.identity.ein_clean:
            keys.append(f"ein:{persona.identity.ein_clean}")
        if persona.identity.phone_digits:
            keys.append(f"phone:{persona.identity.phone_digits}")
        if persona.identity.email_domain:
            keys.append(f"email_domain:{persona.identity.email_domain.lower()}")
        return keys

    def _build_embedding_text(self, persona: ClassifiedPersona) -> str:
        """Build composite text for embedding (same format as sync_service)."""
        parts = []
        if persona.identity.normalized_name:
            parts.append(persona.identity.normalized_name)
        if persona.industry.original_category:
            parts.append(persona.industry.original_category)
        loc_parts = [persona.location.city_norm or "", persona.location.state or ""]
        loc = " ".join(p for p in loc_parts if p)
        if loc:
            parts.append(loc)
        keywords = persona.commodity.top_keywords or []
        if keywords:
            parts.append(" ".join(keywords[:5]))
        return " | ".join(parts) if parts else ""

    def find_candidates_for_entity(self, entity_id: str, max_candidates: int = 10) -> dict:
        """Find candidate golden records for an existing entity.

        Uses stored embedding if available, otherwise computes one from persona.
        Falls back to bucket-key search if vector search is unavailable.
        """
        start = time.time()
        entity = self._entity_repo.get(entity_id)
        if not entity:
            return {"candidates": [], "error": f"Entity {entity_id} not found", "duration_ms": 0}

        persona = _parse_persona(entity.get("persona", {}))
        classified = _to_classified_persona(persona)
        candidate_scores: dict[str, float] = {}
        candidate_sources: dict[str, list[str]] = {}

        # ── Layer 1: Identity anchors from entity's persona ──
        identity_keys = self._identity_bucket_keys(classified)
        for bk in identity_keys:
            members = self._entity_repo.find_by_bucket_key(bk)
            for gr_id in members:
                if gr_id == entity_id:
                    continue
                candidate_scores[gr_id] = 1.0
                candidate_sources.setdefault(gr_id, []).append(bk)

        # ── Layer 2: Vector search ──
        vector_search_used = False
        # Prefer stored embedding, fall back to computing from persona text
        query_vector = entity.get("embedding")
        if not query_vector or not isinstance(query_vector, list):
            embedding_text = self._build_embedding_text(classified)
            if embedding_text:
                query_vector = self._embedding.embed_text(embedding_text)

        if query_vector:
            state = classified.location.state or None
            vector_results = self._entity_repo.vector_search(
                query_vector=query_vector,
                state_filter=state,
                top_k=max_candidates,
            )
            if vector_results:
                vector_search_used = True
                for vr in vector_results:
                    gr_id = vr["golden_record_id"]
                    if gr_id == entity_id:
                        continue
                    vscore = vr["score"]
                    if gr_id not in candidate_scores:
                        candidate_scores[gr_id] = vscore
                    candidate_sources.setdefault(gr_id, []).append(f"vector:{vscore:.3f}")

        # ── Layer 3: Bucket-key fallback ──
        if not vector_search_used:
            keys = generate_bucket_keys(classified, max_commodity_kw=self._cfg.buckets.max_commodity_keywords)
            for bk in keys:
                if bk in identity_keys:
                    continue
                members = self._entity_repo.find_by_bucket_key(bk)
                for gr_id in members:
                    if gr_id == entity_id:
                        continue
                    if gr_id not in candidate_scores:
                        candidate_scores[gr_id] = 0.5
                    candidate_sources.setdefault(gr_id, []).append(bk)

        # ── Rank and build results ──
        sorted_candidates = sorted(
            candidate_scores.items(), key=lambda x: x[1], reverse=True,
        )[:max_candidates]

        candidates = []
        for gr_id, score in sorted_candidates:
            gr_data = self._entity_repo.get(gr_id)
            if not gr_data:
                continue
            # Skip non-ACTIVE entities (MERGED, PROVISIONAL, etc.)
            if gr_data.get("status") not in (None, "ACTIVE"):
                continue
            candidates.append({
                "golden_record_id": gr_id,
                "canonical_name": gr_data.get("canonical_name", ""),
                "name_variants": _parse_list(gr_data.get("name_variants", [])),
                "persona": _parse_persona(gr_data.get("persona", {})),
                "source_count": int(gr_data.get("source_count", 1)),
                "confidence": float(gr_data.get("confidence", 0.5)),
                "matched_via_buckets": candidate_sources.get(gr_id, []),
                "score": score,
            })

        elapsed = int((time.time() - start) * 1000)
        return {"candidates": candidates, "duration_ms": elapsed}

    def compare_fields(
        self, orphan_persona: dict, candidate: dict,
        ontology_query_fn=None,
    ) -> dict:
        """Deterministic field-by-field comparison across 5 persona dimensions."""
        persona = _to_classified_persona(orphan_persona)
        cand_persona = _to_classified_persona(candidate.get("persona", {}))
        cand_variants = candidate.get("name_variants", [])

        # Hard disqualifiers
        o_ein = persona.identity.ein_clean
        c_ein = cand_persona.identity.ein_clean
        if o_ein and c_ein and o_ein != c_ein:
            return ComparisonResult(
                disqualified=True, disqualification_reason="Different EIN",
            ).model_dump()

        o_state = persona.location.state
        c_state = cand_persona.location.state
        if o_state and c_state and o_state.upper() != c_state.upper():
            return ComparisonResult(
                disqualified=True, disqualification_reason="Different state",
            ).model_dump()

        # Score each dimension
        identity = scoring.score_identity(persona, cand_persona, cand_variants)

        ontology_score = None
        if persona.industry.naics_code and cand_persona.industry.naics_code:
            o_sec = persona.industry.naics_code[:2]
            c_sec = cand_persona.industry.naics_code[:2]
            if o_sec != c_sec and ontology_query_fn:
                ontology_result = ontology_query_fn(
                    "INDUSTRY_RELATION",
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

        # ── EIN/name fast-paths (bypass composite calculation) ──
        ein_exact = identity.details.get("ein_match") == "EXACT"
        same_state = (o_state and c_state
                      and o_state.upper() == c_state.upper())
        same_city = (persona.location.city_norm and cand_persona.location.city_norm
                     and persona.location.city_norm.upper() == cand_persona.location.city_norm.upper())
        name_sim = identity.details.get("name_similarity", 0.0)

        # EIN exact match + same state → definitive match (0.95)
        if ein_exact and same_state:
            base_weights = self._cfg.weights.as_dict()
            return ComparisonResult(
                identity=identity, industry=industry, location=location,
                commodity=commodity, behavioral=behavioral,
                composite=0.95, weights_used=base_weights,
                sparsity_adjusted=False, disqualified=False,
            ).model_dump()

        # Strong name match (JW >= 0.95) + same state + same city → 0.90
        if name_sim >= 0.95 and same_state and same_city:
            base_weights = self._cfg.weights.as_dict()
            return ComparisonResult(
                identity=identity, industry=industry, location=location,
                commodity=commodity, behavioral=behavioral,
                composite=0.90, weights_used=base_weights,
                sparsity_adjusted=False, disqualified=False,
            ).model_dump()

        base_weights = self._cfg.weights.as_dict()
        composite, weights_used, sparsity_adj = scoring.compute_composite(dimensions, base_weights)

        return ComparisonResult(
            identity=identity, industry=industry, location=location,
            commodity=commodity, behavioral=behavioral,
            composite=composite, weights_used=weights_used,
            sparsity_adjusted=sparsity_adj, disqualified=False,
        ).model_dump()

    def semantic_similarity(self, orphan_persona: dict, candidate: dict) -> dict:
        """Compute semantic similarity via embeddings."""
        persona = _to_classified_persona(orphan_persona)
        cand_persona = _to_classified_persona(candidate.get("persona", {}))

        orphan_texts = _persona_to_texts(persona)
        candidate_texts = _persona_to_texts(cand_persona)

        weights = self._cfg.weights.as_dict()
        result = self._embedding.compute_similarity(orphan_texts, candidate_texts, weights)

        return SimilarityResult(
            name_similarity=result.get("name_similarity", 0.0),
            industry_similarity=result.get("industry_similarity", 0.0),
            commodity_similarity=result.get("commodity_similarity", 0.0),
            location_similarity=result.get("location_similarity", 0.0),
            composite_similarity=result.get("composite_similarity", 0.0),
            model_used=result.get("model_used", ""),
            inference_ms=result.get("inference_ms", 0),
        ).model_dump()
