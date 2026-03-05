"""
Resolution service — the agent's brain for resolving orphan records.

Escalation strategy (3 steps):
  Step 1: find_candidates (vector search + identity anchors) → if 0 → create.
  Step 2: compare_fields + blend vector score → if >0.85 → merge.
          All <0.40 → create. Ambiguous → Step 3.
  Step 3: LLM reasoning → final decision (MERGE/REVIEW/NEW_ENTITY).
  Write action + log_decision (always).
"""
from __future__ import annotations

import asyncio
import logging
import time

from interfaces.candidate_finder import AbstractCandidateFinder
from interfaces.field_comparator import AbstractFieldComparator
from interfaces.similarity_provider import AbstractSimilarityProvider
from interfaces.llm_reasoner import AbstractLLMReasoner
from interfaces.entity_store import AbstractEntityStore
from interfaces.audit_logger import AbstractAuditLogger

from models.persona import ClassifiedPersona
from models.resolution import (
    ResolutionRequest, ResolutionResponse,
    Decision, MatchLevel, DimensionScores, EvaluationStep, CandidateMatch,
    ComparisonResult, SimilarityResult,
)
from config import AgentConfig
from utils import telemetry

logger = logging.getLogger(__name__)


class ResolutionService:
    """Resolves orphan records against the golden record corpus.

    Depends on abstract interfaces — all data access goes through injected providers.
    """

    def __init__(
        self,
        finder: AbstractCandidateFinder,
        comparator: AbstractFieldComparator,
        similarity: AbstractSimilarityProvider,
        reasoner: AbstractLLMReasoner,
        store: AbstractEntityStore,
        audit: AbstractAuditLogger,
        config: AgentConfig,
    ):
        self._finder = finder
        self._comparator = comparator
        self._similarity = similarity
        self._reasoner = reasoner
        self._store = store
        self._audit = audit
        self._cfg = config

    async def resolve(self, request: ResolutionRequest) -> ResolutionResponse:
        """Main resolution: evaluate orphan persona against candidates."""
        start = time.time()
        chain: list[EvaluationStep] = []
        llm_calls = 0
        embedding_calls = 0
        persona = request.classified_persona

        telemetry.inc_active()

        with telemetry.span("resolve", {
            "event_id": request.event_id,
            "record_id": request.record_id,
            "chain_depth": request.chain_depth,
        }) as root_span:
          try:
            # ── Step 1: Find candidates ────────────────────────────
            with telemetry.span("step.find_candidates") as s1:
                t0 = time.time()
                result = await self._finder.find(persona.model_dump())
                candidates = result["candidates"]
                step_ms = result.get("duration_ms", int((time.time() - t0) * 1000))
                s1.set_attribute("candidates_found", len(candidates))
                s1.set_attribute("buckets_checked", result["bucket_stats"].get("total_candidates", 0))
                telemetry.record_step_duration("find_candidates", step_ms, "mcp_server")
                telemetry.record_candidate_count(len(candidates))

            chain.append(EvaluationStep(
                step="find_candidates",
                tool_called="mcp:find_candidates",
                duration_ms=step_ms,
                details={
                    "candidates_found": len(candidates),
                    "buckets_checked": result["bucket_stats"].get("total_candidates", 0),
                },
            ))

            # No candidates → create new entity
            if not candidates:
                resp = await self._create_new(
                    request, persona, chain, llm_calls, embedding_calls, start,
                    reason="No candidates found in any bucket",
                )
                root_span.set_attribute("decision", resp.decision.value)
                return resp

            # ── Step 2: Compare + score each candidate ─────────────
            # Blends deterministic field comparison with vector similarity
            # from Step 1 into a single combined score.
            scored: list[CandidateMatch] = []
            for cand in candidates:
                with telemetry.span("step.compare_fields", {"candidate": cand["golden_record_id"]}) as s2:
                    t1 = time.time()
                    cmp_dict = await self._comparator.compare(persona.model_dump(), cand)
                    cmp_ms = int((time.time() - t1) * 1000)
                    comparison = ComparisonResult.model_validate(cmp_dict)
                    s2.set_attribute("composite", comparison.composite)
                    s2.set_attribute("disqualified", comparison.disqualified)
                    telemetry.record_step_duration("compare_fields", cmp_ms, "mcp_server")

                chain.append(EvaluationStep(
                    step="compare_fields",
                    tool_called="mcp:compare_fields",
                    candidate=cand["golden_record_id"],
                    score=comparison.composite,
                    disqualified=comparison.disqualified,
                    duration_ms=cmp_ms,
                    details={"disqualification_reason": comparison.disqualification_reason}
                    if comparison.disqualified else {},
                ))

                if comparison.disqualified:
                    continue

                # Name gate: skip candidates where name similarity (Jaro-Winkler)
                # is below threshold — even if EIN/phone/email pushed aggregate
                # identity score higher. Checked BEFORE vector blending.
                name_sim = comparison.identity.details.get("name_similarity", 0.0)
                if name_sim < self._cfg.thresholds.min_identity_score:
                    chain.append(EvaluationStep(
                        step="name_gate_skip",
                        tool_called="orchestrator",
                        candidate=cand["golden_record_id"],
                        score=name_sim,
                        details={"reason": f"name_similarity {name_sim:.2f} < {self._cfg.thresholds.min_identity_score}"},
                    ))
                    logger.info(
                        "NAME_GATE_SKIP cand=%s name_sim=%.3f threshold=%.2f",
                        cand["golden_record_id"], name_sim, self._cfg.thresholds.min_identity_score,
                    )
                    continue

                # Blend in vector score from find_candidates
                vector_score = _extract_vector_score(cand)
                if vector_score is not None and comparison.identity.score >= 0.55:
                    combined = round(
                        (comparison.composite * 0.6) + (vector_score * 0.4), 4
                    )
                elif vector_score is not None:
                    combined = round(
                        (comparison.composite * 0.85) + (vector_score * 0.15), 4
                    )
                else:
                    combined = comparison.composite

                cm = CandidateMatch(
                    golden_record_id=cand["golden_record_id"],
                    canonical_name=cand["canonical_name"],
                    comparison=comparison,
                    combined_score=combined,
                )
                if vector_score is not None:
                    cm.similarity = SimilarityResult(
                        composite_similarity=vector_score,
                        model_used="neo4j_vector",
                        inference_ms=0,
                    )

                # Above auto-merge threshold → immediate merge
                if combined > self._cfg.thresholds.auto_merge:
                    cm.match_level = MatchLevel.DETERMINISTIC
                    resp = await self._merge(
                        request, persona, cm, chain, llm_calls, embedding_calls, start,
                    )
                    root_span.set_attribute("decision", resp.decision.value)
                    root_span.set_attribute("match_level", "DETERMINISTIC")
                    return resp

                scored.append(cm)

            # All disqualified or below threshold → create new
            ambiguous = [c for c in scored if c.combined_score >= self._cfg.thresholds.embedding_needed_low]
            if not ambiguous:
                resp = await self._create_new(
                    request, persona, chain, llm_calls, embedding_calls, start,
                    reason="All candidates below minimum threshold or disqualified",
                )
                root_span.set_attribute("decision", resp.decision.value)
                return resp

            # ── Fast mode: deterministic only, skip LLM ──
            if request.fast_mode:
                best = max(ambiguous, key=lambda c: c.combined_score)
                if best.combined_score >= self._cfg.thresholds.auto_merge:
                    best.match_level = MatchLevel.DETERMINISTIC
                    resp = await self._merge(
                        request, persona, best, chain, llm_calls, embedding_calls, start,
                    )
                    root_span.set_attribute("decision", resp.decision.value)
                    root_span.set_attribute("match_level", "DETERMINISTIC")
                    root_span.set_attribute("fast_mode", True)
                    return resp
                total_ms = int((time.time() - start) * 1000)
                root_span.set_attribute("decision", "REVIEW")
                root_span.set_attribute("fast_mode", True)
                return ResolutionResponse(
                    event_id=request.event_id,
                    decision=Decision.REVIEW,
                    target_golden_record_id=best.golden_record_id,
                    confidence=best.combined_score,
                    dimension_scores=_extract_dim_scores(best),
                    reasoning=f"Fast mode: composite {best.combined_score:.2f} below auto-merge, deferred to full pass",
                    key_factors=_build_key_factors(best),
                    evaluation_chain=chain,
                    agent_metadata={
                        "total_duration_ms": total_ms,
                        "llm_calls": 0,
                        "embedding_calls": 0,
                        "fast_mode_deferred": True,
                    },
                )

            # ── Step 3: LLM reasoning ──────────────────────────────
            # Cascade guard: if chain_depth >= limit, force REVIEW
            if request.chain_depth >= self._cfg.re_evaluation.force_review_at_depth:
                best = max(ambiguous, key=lambda c: c.combined_score)
                resp = await self._submit_review(
                    request, persona, best, chain, llm_calls, embedding_calls, start,
                    reason=f"Cascade guard: chain_depth={request.chain_depth} >= {self._cfg.re_evaluation.force_review_at_depth}",
                    forced=True,
                )
                root_span.set_attribute("decision", resp.decision.value)
                root_span.set_attribute("cascade_guard", True)
                return resp

            # Build evidence for LLM
            evidence = _build_llm_evidence(persona, ambiguous, chain)
            with telemetry.span("step.llm_reasoning") as s4:
                t3 = time.time()
                llm_result = await asyncio.to_thread(self._reasoner.reason, evidence)
                llm_calls += 1
                llm_ms = llm_result.get("llm_duration_ms", int((time.time() - t3) * 1000))
                telemetry.record_llm_call(llm_result.get("model_used", ""), not llm_result.get("fallback", False))
                s4.set_attribute("decision", llm_result.get("decision", ""))
                s4.set_attribute("confidence", llm_result.get("confidence", 0))
                s4.set_attribute("fallback", llm_result.get("fallback", False))
                telemetry.record_step_duration("llm_reasoning", llm_ms, "llm")

            chain.append(EvaluationStep(
                step="llm_reasoning",
                tool_called="llm_client.reason",
                duration_ms=llm_ms,
                details={
                    "model": llm_result.get("model_used", ""),
                    "decision": llm_result.get("decision", ""),
                    "confidence": llm_result.get("confidence", 0),
                    "fallback": llm_result.get("fallback", False),
                },
            ))

            # Route based on LLM decision
            llm_decision = llm_result.get("decision", "REVIEW")
            llm_confidence = llm_result.get("confidence", 0.5)
            llm_target = llm_result.get("target_golden_record_id")

            if llm_decision == "MERGE" and llm_target:
                target_cm = next(
                    (c for c in ambiguous if c.golden_record_id == llm_target), None
                )
                if target_cm:
                    target_cm.combined_score = llm_confidence
                    target_cm.match_level = MatchLevel.LLM
                    resp = await self._merge(
                        request, persona, target_cm, chain, llm_calls, embedding_calls, start,
                    )
                    root_span.set_attribute("decision", resp.decision.value)
                    root_span.set_attribute("match_level", "LLM")
                    return resp

            if llm_decision == "NEW_ENTITY":
                resp = await self._create_new(
                    request, persona, chain, llm_calls, embedding_calls, start,
                    reason=llm_result.get("reasoning", "LLM determined no match"),
                )
                root_span.set_attribute("decision", resp.decision.value)
                return resp

            # Default: REVIEW
            best = max(ambiguous, key=lambda c: c.combined_score)
            resp = await self._submit_review(
                request, persona, best, chain, llm_calls, embedding_calls, start,
                reason=llm_result.get("reasoning", "LLM recommended review"),
                key_uncertainty=llm_result.get("key_uncertainty", ""),
            )
            root_span.set_attribute("decision", resp.decision.value)
            return resp

          except Exception as e:
            telemetry.record_error(type(e).__name__, "resolve")
            raise
          finally:
            total_ms = int((time.time() - start) * 1000)
            root_span.set_attribute("total_duration_ms", total_ms)
            root_span.set_attribute("llm_calls", llm_calls)
            root_span.set_attribute("embedding_calls", embedding_calls)
            telemetry.dec_active()

    # ── Internal actions ────────────────────────────────────

    async def _merge(
        self, request, persona, candidate, chain, llm_calls, embedding_calls, start,
    ) -> ResolutionResponse:
        """Execute a merge and log it."""
        t = time.time()
        merge_result = await self._store.merge(
            orphan_record_id=request.record_id,
            orphan_persona=persona.model_dump() if hasattr(persona, "model_dump") else persona,
            golden_record_id=candidate.golden_record_id,
            merge_reasoning={
                "trigger": f"AI_AGENT_{candidate.match_level.value}",
                "confidence": candidate.combined_score,
                "dimension_scores": _extract_dim_scores(candidate).__dict__,
            },
            company_id=str(request.company_id),
            record_type=request.record_type,
        )
        chain.append(EvaluationStep(
            step="merge", tool_called="mcp:merge_into_golden_record",
            candidate=candidate.golden_record_id,
            score=candidate.combined_score,
            duration_ms=merge_result.get("duration_ms", int((time.time() - t) * 1000)),
        ))

        dim_scores = _extract_dim_scores(candidate)
        total_ms = int((time.time() - start) * 1000)

        audit_metadata = {
            "trigger_type": f"AI_AGENT_{candidate.match_level.value}",
            "total_duration_ms": total_ms,
            "llm_calls": llm_calls,
            "embedding_calls": embedding_calls,
            "candidates_evaluated": len([s for s in chain if s.step == "compare_fields"]),
        }
        dim_scores_dict = dim_scores.__dict__ if isinstance(dim_scores, DimensionScores) else dim_scores
        eval_chain_list = [s.model_dump() for s in chain]
        merge_key_factors = _build_key_factors(candidate)
        merge_reasoning = f"Merged into {candidate.canonical_name} via {candidate.match_level.value}"

        await self._audit.log_decision(
            event_id=request.event_id,
            record_id=request.record_id,
            decision="MERGE",
            target_golden_record_id=candidate.golden_record_id,
            confidence=candidate.combined_score,
            dimension_scores=dim_scores_dict,
            reasoning=merge_reasoning,
            key_factors=merge_key_factors,
            evaluation_chain=eval_chain_list,
            agent_metadata=audit_metadata,
        )

        total_ms = int((time.time() - start) * 1000)
        telemetry.record_resolution_duration(total_ms, "MERGE", candidate.match_level.value)

        return ResolutionResponse(
            event_id=request.event_id,
            decision=Decision.MERGE,
            target_golden_record_id=candidate.golden_record_id,
            confidence=candidate.combined_score,
            dimension_scores=dim_scores,
            reasoning=f"Merged into {candidate.canonical_name} ({candidate.match_level.value})",
            key_factors=merge_key_factors,
            evaluation_chain=chain,
            agent_metadata=audit_metadata,
            golden_record_after=merge_result.get("golden_record_after"),
            relationship=merge_result.get("relationship"),
            audit_record={
                "audit_id": f"A-{request.event_id[:8]}",
                "event_id": request.event_id, "record_id": request.record_id,
                "perspective": "GLOBAL",
                "decision": "MERGE", "target_golden_id": candidate.golden_record_id,
                "absorbed_golden_id": merge_result.get("absorbed_golden_id"),
                "confidence": candidate.combined_score,
                "dimension_scores": dim_scores_dict,
                "reasoning": merge_reasoning, "key_factors": merge_key_factors,
                "evaluation_chain": eval_chain_list,
                "golden_record_before": merge_result.get("golden_record_before"),
                "golden_record_after": merge_result.get("golden_record_after"),
                **audit_metadata,
            },
        )

    async def _create_new(
        self, request, persona, chain, llm_calls, embedding_calls, start, reason="",
    ) -> ResolutionResponse:
        """Create a new golden record and log it."""
        t = time.time()
        create_result = await self._store.create(
            orphan_record_id=request.record_id,
            orphan_persona=persona.model_dump() if hasattr(persona, "model_dump") else persona,
            creation_reasoning={"trigger": "AI_AGENT_NEW", "reasoning": reason},
            company_id=str(request.company_id),
            record_type=request.record_type,
        )
        chain.append(EvaluationStep(
            step="create", tool_called="mcp:create_golden_record",
            duration_ms=create_result.get("duration_ms", int((time.time() - t) * 1000)),
            details={"golden_record_id": create_result.get("golden_record_id")},
        ))

        total_ms = int((time.time() - start) * 1000)
        telemetry.record_resolution_duration(total_ms, "NEW_ENTITY")

        audit_metadata = {
            "trigger_type": "AI_AGENT_NEW",
            "total_duration_ms": total_ms,
            "llm_calls": llm_calls,
            "embedding_calls": embedding_calls,
            "candidates_evaluated": len([s for s in chain if s.step == "compare_fields"]),
        }
        eval_chain_list = [s.model_dump() for s in chain]
        await self._audit.log_decision(
            event_id=request.event_id,
            record_id=request.record_id,
            decision="NEW_ENTITY",
            target_golden_record_id=None,
            confidence=0.0,
            dimension_scores={},
            reasoning=reason,
            key_factors=["no_match"],
            evaluation_chain=eval_chain_list,
            agent_metadata=audit_metadata,
        )

        return ResolutionResponse(
            event_id=request.event_id,
            decision=Decision.NEW_ENTITY,
            target_golden_record_id=create_result.get("golden_record_id"),
            confidence=0.0,
            reasoning=reason,
            key_factors=["no_match"],
            evaluation_chain=chain,
            agent_metadata=audit_metadata,
            golden_record_after=create_result.get("golden_record_after"),
            relationship=create_result.get("relationship"),
            audit_record={
                "audit_id": f"A-{request.event_id[:8]}",
                "event_id": request.event_id, "record_id": request.record_id,
                "perspective": "GLOBAL",
                "decision": "NEW_ENTITY", "target_golden_id": create_result.get("golden_record_id"),
                "confidence": 0.0, "dimension_scores": {},
                "reasoning": reason, "key_factors": ["no_match"],
                "evaluation_chain": eval_chain_list,
                "golden_record_before": None,
                "golden_record_after": create_result.get("golden_record_after"),
                **audit_metadata,
            },
        )

    async def _submit_review(
        self, request, persona, candidate, chain, llm_calls, embedding_calls, start,
        reason="", key_uncertainty="", forced=False,
    ) -> ResolutionResponse:
        """Submit to human review and log it."""
        t = time.time()
        review_result = await self._store.submit_for_review(
            orphan_record_id=request.record_id,
            orphan_persona=persona.model_dump() if hasattr(persona, "model_dump") else persona,
            candidate_golden_record_id=candidate.golden_record_id,
            review_reasoning={
                "confidence": candidate.combined_score,
                "dimension_scores": _extract_dim_scores(candidate).__dict__,
                "reasoning": reason,
                "key_uncertainty": key_uncertainty,
                "trigger_type": "AI_AGENT_LLM" if llm_calls > 0 else "AI_AGENT_EMBEDDING",
            },
            company_id=str(request.company_id),
            record_type=request.record_type,
        )
        chain.append(EvaluationStep(
            step="submit_review", tool_called="mcp:submit_for_review",
            candidate=candidate.golden_record_id,
            score=candidate.combined_score,
            duration_ms=review_result.get("duration_ms", int((time.time() - t) * 1000)),
            details={"forced": forced},
        ))

        dim_scores = _extract_dim_scores(candidate)
        total_ms = int((time.time() - start) * 1000)
        telemetry.record_resolution_duration(total_ms, "REVIEW")

        dim_scores_dict = dim_scores.__dict__ if isinstance(dim_scores, DimensionScores) else dim_scores
        review_key_factors = _build_key_factors(candidate) + (["cascade_guard"] if forced else [])
        eval_chain_list = [s.model_dump() for s in chain]
        audit_metadata = {
            "trigger_type": "AI_AGENT_LLM" if llm_calls > 0 else "AI_AGENT_EMBEDDING",
            "total_duration_ms": total_ms,
            "llm_calls": llm_calls,
            "embedding_calls": embedding_calls,
            "candidates_evaluated": len([s for s in chain if s.step == "compare_fields"]),
        }

        await self._audit.log_decision(
            event_id=request.event_id,
            record_id=request.record_id,
            decision="REVIEW",
            target_golden_record_id=candidate.golden_record_id,
            confidence=candidate.combined_score,
            dimension_scores=dim_scores_dict,
            reasoning=reason,
            key_factors=review_key_factors,
            evaluation_chain=eval_chain_list,
            agent_metadata=audit_metadata,
        )

        return ResolutionResponse(
            event_id=request.event_id,
            decision=Decision.REVIEW,
            target_golden_record_id=candidate.golden_record_id,
            confidence=candidate.combined_score,
            dimension_scores=dim_scores,
            reasoning=reason,
            key_factors=_build_key_factors(candidate),
            evaluation_chain=chain,
            agent_metadata=audit_metadata,
            golden_record_after=review_result.get("golden_record_after"),
            relationship=review_result.get("relationship"),
            pending_resolution=review_result.get("pending_resolution"),
            audit_record={
                "audit_id": f"A-{request.event_id[:8]}",
                "event_id": request.event_id, "record_id": request.record_id,
                "perspective": "GLOBAL",
                "decision": "REVIEW", "target_golden_id": candidate.golden_record_id,
                "confidence": candidate.combined_score,
                "dimension_scores": dim_scores_dict,
                "reasoning": reason, "key_factors": review_key_factors,
                "evaluation_chain": eval_chain_list,
                "golden_record_before": None,
                "golden_record_after": None,
                **audit_metadata,
            },
        )


# ── Utility functions ───────────────────────────────────────

def _extract_vector_score(cand_data: dict) -> float | None:
    """Extract vector similarity score from matched_via_buckets if present.

    Candidate service appends entries like "vector:0.847" when the candidate
    was found via Neo4j vector search. Returns the float score or None.
    """
    for bucket in cand_data.get("matched_via_buckets", []):
        if isinstance(bucket, str) and bucket.startswith("vector:"):
            try:
                return float(bucket.split(":", 1)[1])
            except (ValueError, IndexError):
                continue
    return None


def _build_llm_evidence(
    persona: ClassifiedPersona, candidates: list[CandidateMatch], chain: list
) -> dict:
    """Build evidence dict for LLM reasoning."""
    cand_evidence = []
    for cm in candidates:
        entry = {
            "golden_record_id": cm.golden_record_id,
            "canonical_name": cm.canonical_name,
        }
        if cm.comparison:
            entry["comparison"] = {
                "composite": cm.comparison.composite,
                "identity": {"score": cm.comparison.identity.score, "details": cm.comparison.identity.details},
                "industry": {"score": cm.comparison.industry.score, "details": cm.comparison.industry.details},
                "location": {"score": cm.comparison.location.score, "details": cm.comparison.location.details},
                "commodity": {"score": cm.comparison.commodity.score, "details": cm.comparison.commodity.details},
                "behavioral": {"score": cm.comparison.behavioral.score, "details": cm.comparison.behavioral.details},
            }
        if cm.similarity:
            entry["similarity"] = {
                "name": cm.similarity.name_similarity,
                "industry": cm.similarity.industry_similarity,
                "commodity": cm.similarity.commodity_similarity,
                "location": cm.similarity.location_similarity,
                "composite": cm.similarity.composite_similarity,
            }
        cand_evidence.append(entry)

    return {
        "orphan_persona": persona.model_dump(),
        "candidates": cand_evidence,
        "evaluation_steps": [f"{s.step}: {s.candidate or ''} score={s.score}" for s in chain],
    }


def _extract_dim_scores(cm: CandidateMatch) -> DimensionScores:
    if cm.comparison:
        return DimensionScores(
            identity=cm.comparison.identity.score,
            industry=cm.comparison.industry.score,
            location=cm.comparison.location.score,
            commodity=cm.comparison.commodity.score,
            behavioral=cm.comparison.behavioral.score,
        )
    return DimensionScores()


def _build_key_factors(cm: CandidateMatch) -> list[str]:
    factors = []
    if cm.comparison:
        c = cm.comparison
        if c.identity.score > 0.8:
            factors.append("strong_identity_match")
        if c.identity.details.get("ein_match") == "EXACT":
            factors.append("EIN_exact")
        if c.industry.score > 0.8:
            factors.append("industry_match")
        if c.industry.details.get("ontology_consulted"):
            factors.append("ontology_cross_taxonomy")
        if c.location.score > 0.7:
            factors.append("same_location")
        if c.commodity.score > 0.5:
            factors.append(f"commodity_overlap_{c.commodity.score:.0%}")
    if cm.similarity and cm.similarity.composite_similarity > 0.7:
        factors.append("strong_semantic_similarity")
    return factors
