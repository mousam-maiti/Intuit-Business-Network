"""
Re-evaluation service — re-evaluates golden records after enrichment.

When a merge adds new bucket keys, checks if other golden records
in those buckets should also be merged.

Extracted from orchestrator.py re_evaluate() method.
"""
from __future__ import annotations

import logging
import time

from interfaces.candidate_finder import AbstractCandidateFinder
from interfaces.field_comparator import AbstractFieldComparator
from interfaces.entity_store import AbstractEntityStore

from models.persona import (
    ClassifiedPersona, IdentityDimension, IndustryDimension,
    LocationDimension, CommodityDimension, BehavioralDimension,
)
from models.resolution import (
    ReEvaluationRequest, ReEvaluationResponse,
    ComparisonResult, EvaluationStep,
)
from config import AgentConfig

logger = logging.getLogger(__name__)


class ReEvaluationService:
    """Re-evaluates golden records after enrichment adds new bucket keys.

    Depends on abstract interfaces for candidate finding, field comparison,
    and entity store operations.
    """

    def __init__(
        self,
        finder: AbstractCandidateFinder,
        comparator: AbstractFieldComparator,
        store: AbstractEntityStore,
        config: AgentConfig,
    ):
        self._finder = finder
        self._comparator = comparator
        self._store = store
        self._cfg = config

    async def re_evaluate(self, request: ReEvaluationRequest) -> ReEvaluationResponse:
        """Re-evaluate a golden record against potential duplicates."""
        start = time.time()
        chain: list[EvaluationStep] = []
        merges = []
        reviews = []

        # Step 1: Get golden record profile
        entity_result = await self._store.describe(request.golden_record_id)
        if entity_result.get("error") or not entity_result.get("entity"):
            return ReEvaluationResponse(
                golden_record_id=request.golden_record_id,
                evaluation_chain=[EvaluationStep(
                    step="error", tool_called="mcp:describe_entity",
                    details={"error": entity_result.get("error", "Entity not found")},
                )],
            )

        # Build persona from entity profile
        persona = _build_persona_from_entity(entity_result["entity"])

        # Step 2: Find candidates (includes new bucket key matches)
        cand_result = await self._finder.find(persona.model_dump())
        candidates = cand_result.get("candidates", [])

        # Filter out self
        candidates = [c for c in candidates if c["golden_record_id"] != request.golden_record_id]

        if not candidates:
            return ReEvaluationResponse(
                golden_record_id=request.golden_record_id,
                no_match_count=0,
                evaluation_chain=[EvaluationStep(
                    step="find_candidates", tool_called="mcp:find_candidates",
                    details={"candidates": 0},
                )],
            )

        # Step 3: Compare each candidate
        for cand in candidates:
            cand_id = cand["golden_record_id"]
            cmp_dict = await self._comparator.compare(persona.model_dump(), cand)
            comparison = ComparisonResult.model_validate(cmp_dict)

            chain.append(EvaluationStep(
                step="re_eval_compare",
                tool_called="mcp:compare_fields",
                candidate=cand_id,
                score=comparison.composite,
                disqualified=comparison.disqualified,
            ))

            if comparison.disqualified or comparison.composite < self._cfg.thresholds.embedding_needed_low:
                continue

            # Name gate: skip candidates with weak name similarity
            name_sim = comparison.identity.details.get("name_similarity", 0.0)
            if name_sim < self._cfg.thresholds.min_identity_score:
                continue

            # Above merge threshold and chain_depth allows
            if (comparison.composite > self._cfg.thresholds.auto_merge
                    and request.chain_depth < self._cfg.re_evaluation.force_review_at_depth):
                result = await self._store.merge_golden_records(
                    survivor_id=request.golden_record_id,
                    absorbed_id=cand_id,
                    merge_reasoning={"confidence": comparison.composite},
                )
                merges.append(result)
            elif comparison.composite >= self._cfg.thresholds.human_review:
                reviews.append({
                    "candidate_id": cand_id,
                    "score": comparison.composite,
                })

        elapsed = int((time.time() - start) * 1000)
        return ReEvaluationResponse(
            golden_record_id=request.golden_record_id,
            merges=merges,
            reviews=reviews,
            no_match_count=len(candidates) - len(merges) - len(reviews),
            evaluation_chain=chain,
        )


def _build_persona_from_entity(entity: dict) -> ClassifiedPersona:
    """Reconstruct ClassifiedPersona from describe_entity response."""
    ident = entity.get("identity", {})
    ind = entity.get("industry", {})
    loc = entity.get("location", {})
    comm = entity.get("commodity", {})
    behav = entity.get("behavioral", {})

    return ClassifiedPersona(
        identity=IdentityDimension(
            normalized_name=entity.get("canonical_name", ""),
            name_first_token=entity.get("canonical_name", "").split()[0].upper() if entity.get("canonical_name") else "",
            ein_clean=ident.get("ein") or "",
            phone_digits=ident.get("phone") or "",
            email=ident.get("email") or "",
            email_domain=(ident.get("email") or "").split("@")[-1] if ident.get("email") else "",
        ),
        industry=IndustryDimension(
            naics_code=ind.get("naics_code") or "",
            naics_sector=ind.get("naics_sector") or "",
            naics_subsector=ind.get("naics_subsector") or "",
        ),
        location=LocationDimension(
            state=loc.get("state") or "",
            city_norm=loc.get("city") or "",
            zip5=loc.get("zip5") or "",
            zip3=loc.get("zip3") or "",
        ),
        commodity=CommodityDimension(
            top_keywords=comm.get("top_keywords") or [],
        ),
        behavioral=BehavioralDimension(
            volume_bracket=behav.get("volume_bracket") or "",
            avg_transaction=float(behav.get("avg_transaction") or 0),
            transaction_count=int(behav.get("transaction_count") or 0),
        ),
    )
