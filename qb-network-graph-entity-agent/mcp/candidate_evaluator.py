"""
MCP Server 1: candidate_evaluator — All read-side analysis.

3 tools: find_candidates, compare_fields, semantic_similarity

v3 changes:
  - find_candidates: MySQL indexed queries replace Redis bucket sorted sets
  - Golden record hydration: MySQL point read replaces Redis hash + Paimon fallback
  - No Redis or Paimon dependency

Connected stores: MySQL (golden records), Gemini API (embeddings)
All read-only — no mutations.

Design doc §2.1.
"""
from __future__ import annotations
import json
import logging
import time
from typing import Optional

from models.persona import ClassifiedPersona, GoldenRecord
from models.resolution import (
    ComparisonResult, DimensionResult, SimilarityResult,
    CandidateMatch, MatchLevel, DimensionConfidence,
)
from clients.mysql_client import MySQLClient
from clients.embedding_client import EmbeddingClient
from utils.bucket_keys import generate_bucket_keys
from utils import scoring
from config import AgentConfig

logger = logging.getLogger(__name__)


class CandidateEvaluator:
    """MCP Server 1: candidate_evaluator — read-only evaluation pipeline.

    v3: MySQL-backed. No Redis or Paimon dependency.
    """

    def __init__(
        self,
        config: AgentConfig,
        mysql: MySQLClient,
        embedding: EmbeddingClient,
        knowledge_graph=None,
    ):
        self._cfg = config
        self._mysql = mysql
        self._embedding = embedding
        self._kg = knowledge_graph

    def set_knowledge_graph(self, kg):
        """Wire cross-dependency: compare_fields → query_ontology."""
        self._kg = kg

    # ── Tool 1: find_candidates ─────────────────────────────

    def find_candidates(
        self,
        orphan_persona: ClassifiedPersona,
        max_candidates: int = 20,
    ) -> dict:
        """Retrieve candidate golden records by persona-dimension bucket keys.

        v3: Queries MySQL indexed columns directly instead of Redis sorted sets.

        Bucket key → MySQL index:
          ein:743218976         → WHERE ein = ?             (idx_gr_ein)
          name:BOBS+TX          → FULLTEXT + state filter   (ft_gr_name + idx_gr_state)
          naics4:4237+TX        → WHERE naics_code LIKE ?   (idx_gr_naics_state)
          zip3:787              → WHERE zip3 = ?            (idx_gr_zip3)
          city:AUSTIN+TX        → WHERE city=? AND state=?  (idx_gr_city_state)

        All sub-10ms at 1M records.
        """
        start = time.time()

        # Generate bucket keys from orphan persona
        keys = generate_bucket_keys(
            orphan_persona,
            max_commodity_kw=self._cfg.buckets.max_commodity_keywords,
        )

        # Query each bucket via MySQL
        candidate_buckets: dict[str, list[str]] = {}  # gr_id → [matched bucket_keys]
        total_before_dedup = 0
        buckets_used = []

        for bk in keys:
            members = self._mysql.find_by_bucket_key(bk)
            buckets_used.append({"key": bk, "candidate_count": len(members)})
            total_before_dedup += len(members)
            for gr_id in members:
                candidate_buckets.setdefault(gr_id, []).append(bk)

        # Sort by bucket overlap count (more shared buckets = stronger signal)
        sorted_candidates = sorted(
            candidate_buckets.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[:max_candidates]

        # Hydrate golden records from MySQL
        candidates = []
        for gr_id, matched_buckets in sorted_candidates:
            gr_data = self._mysql.get_golden_record(gr_id)
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

    # ── Tool 2: compare_fields ──────────────────────────────

    def compare_fields(
        self,
        orphan_persona: ClassifiedPersona,
        candidate: dict,
    ) -> ComparisonResult:
        """Deterministic field-by-field comparison across 5 persona dimensions.

        Hard disqualifiers:
          - EIN mismatch → DISQUALIFY
          - State mismatch → DISQUALIFY

        (Unchanged from v1 — no store dependency.)
        """
        start = time.time()
        cand_persona = _to_classified_persona(candidate.get("persona", {}))
        cand_variants = candidate.get("name_variants", [])

        # ── Hard disqualifiers ──────────────────────────────
        o_ein = orphan_persona.identity.ein_clean
        c_ein = cand_persona.identity.ein_clean
        if o_ein and c_ein and o_ein != c_ein:
            return ComparisonResult(
                disqualified=True,
                disqualification_reason="Different EIN",
            )

        o_state = orphan_persona.location.state
        c_state = cand_persona.location.state
        if o_state and c_state and o_state.upper() != c_state.upper():
            return ComparisonResult(
                disqualified=True,
                disqualification_reason="Different state",
            )

        # ── Score each dimension ────────────────────────────
        identity = scoring.score_identity(orphan_persona, cand_persona, cand_variants)

        # Industry — may call ontology for cross-taxonomy links
        ontology_score = None
        if (orphan_persona.industry.naics_code and cand_persona.industry.naics_code):
            o_sec = orphan_persona.industry.naics_code[:2]
            c_sec = cand_persona.industry.naics_code[:2]
            if o_sec != c_sec and self._kg:
                ontology_result = self._kg.query_ontology(
                    query_type="INDUSTRY_RELATION",
                    code_a=orphan_persona.industry.naics_code,
                    code_b=cand_persona.industry.naics_code,
                )
                if ontology_result.get("cross_taxonomy_links"):
                    ontology_score = 0.40
                elif ontology_result.get("semantic_distance", 1.0) < 0.5:
                    ontology_score = 0.30
                else:
                    ontology_score = 0.0

        industry = scoring.score_industry(orphan_persona, cand_persona, ontology_score)
        location = scoring.score_location(orphan_persona, cand_persona)
        commodity = scoring.score_commodity(orphan_persona, cand_persona)
        behavioral = scoring.score_behavioral(orphan_persona, cand_persona)

        # ── Composite with adaptive weighting ───────────────
        dimensions = {
            "identity": identity,
            "industry": industry,
            "location": location,
            "commodity": commodity,
            "behavioral": behavioral,
        }
        base_weights = self._cfg.weights.as_dict()
        composite, weights_used, sparsity_adj = scoring.compute_composite(
            dimensions, base_weights
        )

        return ComparisonResult(
            identity=identity,
            industry=industry,
            location=location,
            commodity=commodity,
            behavioral=behavioral,
            composite=composite,
            weights_used=weights_used,
            sparsity_adjusted=sparsity_adj,
            disqualified=False,
        )

    # ── Tool 3: semantic_similarity ─────────────────────────

    def semantic_similarity(
        self,
        orphan_persona: ClassifiedPersona,
        candidate: dict,
    ) -> SimilarityResult:
        """Compute semantic similarity via embeddings (Gemini text-embedding-004).

        Called when compare_fields returns ambiguous (0.40-0.85).
        (Unchanged from v1 — no store dependency.)
        """
        cand_persona = _to_classified_persona(candidate.get("persona", {}))

        orphan_texts = _persona_to_texts(orphan_persona)
        candidate_texts = _persona_to_texts(cand_persona)

        weights = self._cfg.weights.as_dict()
        result = self._embedding.compute_similarity(
            orphan_texts, candidate_texts, weights
        )

        return SimilarityResult(
            name_similarity=result.get("name_similarity", 0.0),
            industry_similarity=result.get("industry_similarity", 0.0),
            commodity_similarity=result.get("commodity_similarity", 0.0),
            location_similarity=result.get("location_similarity", 0.0),
            composite_similarity=result.get("composite_similarity", 0.0),
            model_used=result.get("model_used", ""),
            inference_ms=result.get("inference_ms", 0),
        )


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
