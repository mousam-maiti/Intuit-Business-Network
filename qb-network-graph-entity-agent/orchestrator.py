"""
Entity Resolution Orchestrator — the agent's brain.

Calls MCP server tools via Streamable HTTP instead of in-process class methods.

Escalation strategy:
  Step 1: find_candidates → if 0 → create. If found → Step 2.
  Step 2: compare_fields per candidate → if >0.85 → merge. If all <0.40 → create.
          Ambiguous 0.40-0.85 → Step 3.
  Step 3: semantic_similarity → if pushes >0.85 → merge. If <0.40 → create.
          Still ambiguous → Step 4.
  Step 4: LLM reasoning → final decision (MERGE/REVIEW/NEW_ENTITY).
  Step 5: Write action + log_decision (always).

v4: All tool calls go through MCPToolClient → MCP server at :8081.
    Only LLM reasoning stays local.
"""
from __future__ import annotations
import asyncio
import logging
import time
from typing import Optional

from models.persona import ClassifiedPersona
from models.resolution import (
    ResolutionRequest, ResolutionResponse, ReEvaluationRequest, ReEvaluationResponse,
    Decision, MatchLevel, DimensionScores, EvaluationStep, CandidateMatch,
    ComparisonResult, SimilarityResult,
)
from clients.mcp_client import MCPToolClient
from clients.llm_client import LLMClient
from config import AgentConfig
from utils import telemetry

logger = logging.getLogger(__name__)


class Orchestrator:
    """Entity Resolution Agent orchestrator.

    Implements the escalation strategy: deterministic → embedding → LLM.
    The LLM is only called for truly ambiguous cases (~30% of invocations).
    """

    def __init__(
        self,
        config: AgentConfig,
        mcp: MCPToolClient,
        llm: LLMClient,
    ):
        self._cfg = config
        self._mcp = mcp
        self._llm = llm

    # ── POST /resolve ───────────────────────────────────────

    async def resolve(self, request: ResolutionRequest) -> ResolutionResponse:
        """Main resolution endpoint.

        Evaluates orphan persona against candidate golden records
        using escalating comparison: deterministic → embedding → LLM.
        """
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
            # ── Step 1: Find candidates (MCP tool) ────────────────
            with telemetry.span("step.find_candidates") as s1:
                t0 = time.time()
                result = await self._mcp.call_tool("find_candidates", {
                    "orphan_persona": persona.model_dump(),
                })
                candidates = result["candidates"]
                step_ms = result.get("duration_ms", int((time.time() - t0) * 1000))
                s1.set_attribute("candidates_found", len(candidates))
                s1.set_attribute("buckets_checked", result["bucket_stats"]["total_buckets_checked"])
                telemetry.record_step_duration("find_candidates", step_ms, "mcp_server")
                telemetry.record_candidate_count(len(candidates))

            chain.append(EvaluationStep(
                step="find_candidates",
                tool_called="mcp:find_candidates",
                duration_ms=step_ms,
                details={
                    "candidates_found": len(candidates),
                    "buckets_checked": result["bucket_stats"]["total_buckets_checked"],
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

            # ── Step 2: Compare each candidate (MCP tool) ─────────
            scored: list[CandidateMatch] = []
            for cand in candidates:
                with telemetry.span("step.compare_fields", {"candidate": cand["golden_record_id"]}) as s2:
                    t1 = time.time()
                    cmp_dict = await self._mcp.call_tool("compare_fields", {
                        "orphan_persona": persona.model_dump(),
                        "candidate": cand,
                    })
                    cmp_ms = int((time.time() - t1) * 1000)
                    comparison = ComparisonResult.model_validate(cmp_dict)
                    s2.set_attribute("composite", comparison.composite)
                    s2.set_attribute("disqualified", comparison.disqualified)
                    telemetry.record_step_duration("compare_fields", cmp_ms, "mcp_server")

                step = EvaluationStep(
                    step="compare_fields",
                    tool_called="mcp:compare_fields",
                    candidate=cand["golden_record_id"],
                    score=comparison.composite,
                    disqualified=comparison.disqualified,
                    duration_ms=cmp_ms,
                    details={"disqualification_reason": comparison.disqualification_reason}
                    if comparison.disqualified else {},
                )
                chain.append(step)

                if comparison.disqualified:
                    continue

                cm = CandidateMatch(
                    golden_record_id=cand["golden_record_id"],
                    canonical_name=cand["canonical_name"],
                    comparison=comparison,
                    combined_score=comparison.composite,
                )

                # Above auto-merge threshold → immediate merge
                if comparison.composite > self._cfg.thresholds.auto_merge:
                    cm.match_level = MatchLevel.DETERMINISTIC
                    resp = await self._merge(
                        request, persona, cm, chain, llm_calls, embedding_calls, start,
                    )
                    root_span.set_attribute("decision", resp.decision.value)
                    root_span.set_attribute("match_level", "DETERMINISTIC")
                    return resp

                scored.append(cm)

            # All disqualified or below 0.40 → create new
            ambiguous = [c for c in scored if c.combined_score >= self._cfg.thresholds.embedding_needed_low]
            if not ambiguous:
                resp = await self._create_new(
                    request, persona, chain, llm_calls, embedding_calls, start,
                    reason="All candidates below minimum threshold or disqualified",
                )
                root_span.set_attribute("decision", resp.decision.value)
                return resp

            # ── Step 3: Embedding for ambiguous candidates (MCP) ──
            for cm in ambiguous:
                cand_data = next(
                    (c for c in candidates if c["golden_record_id"] == cm.golden_record_id),
                    None,
                )
                if not cand_data:
                    continue

                with telemetry.span("step.semantic_similarity", {"candidate": cm.golden_record_id}) as s3:
                    t2 = time.time()
                    sim_dict = await self._mcp.call_tool("semantic_similarity", {
                        "orphan_persona": persona.model_dump(),
                        "candidate": cand_data,
                    })
                    similarity = SimilarityResult.model_validate(sim_dict)
                    embedding_calls += 1
                    telemetry.record_embedding_call(similarity.model_used, True)
                    s3.set_attribute("composite_similarity", similarity.composite_similarity)
                    s3.set_attribute("model", similarity.model_used)
                    telemetry.record_step_duration("semantic_similarity", similarity.inference_ms, "mcp_server")

                chain.append(EvaluationStep(
                    step="semantic_similarity",
                    tool_called="mcp:semantic_similarity",
                    candidate=cm.golden_record_id,
                    score=similarity.composite_similarity,
                    duration_ms=similarity.inference_ms,
                    details={"model": similarity.model_used},
                ))

                cm.similarity = similarity

                # Combine deterministic + embedding scores
                # Dampen embedding influence when identity is weak — industry
                # embeddings cluster same-sector businesses, confirming "same
                # industry" not "same entity".
                if cm.comparison.identity.score < 0.55:
                    combined = (cm.comparison.composite * 0.85) + (similarity.composite_similarity * 0.15)
                else:
                    combined = (cm.comparison.composite * 0.6) + (similarity.composite_similarity * 0.4)
                cm.combined_score = round(combined, 4)

                if combined > self._cfg.thresholds.auto_merge:
                    cm.match_level = MatchLevel.EMBEDDING
                    resp = await self._merge(
                        request, persona, cm, chain, llm_calls, embedding_calls, start,
                    )
                    root_span.set_attribute("decision", resp.decision.value)
                    root_span.set_attribute("match_level", "EMBEDDING")
                    return resp

            # All still below 0.40 after embedding → create new
            still_ambiguous = [c for c in ambiguous if c.combined_score >= self._cfg.thresholds.embedding_needed_low]
            if not still_ambiguous:
                resp = await self._create_new(
                    request, persona, chain, llm_calls, embedding_calls, start,
                    reason="All candidates below threshold after embedding",
                )
                root_span.set_attribute("decision", resp.decision.value)
                return resp

            # ── Step 4: LLM reasoning (local — not MCP) ───────────
            # Cascade guard: if chain_depth >= 3, force REVIEW
            if request.chain_depth >= self._cfg.re_evaluation.force_review_at_depth:
                best = max(still_ambiguous, key=lambda c: c.combined_score)
                resp = await self._submit_review(
                    request, persona, best, chain, llm_calls, embedding_calls, start,
                    reason=f"Cascade guard: chain_depth={request.chain_depth} >= {self._cfg.re_evaluation.force_review_at_depth}",
                    forced=True,
                )
                root_span.set_attribute("decision", resp.decision.value)
                root_span.set_attribute("cascade_guard", True)
                return resp

            # Build evidence for LLM
            evidence = self._build_llm_evidence(persona, still_ambiguous, chain)
            with telemetry.span("step.llm_reasoning") as s4:
                t3 = time.time()
                llm_result = await asyncio.to_thread(self._llm.reason, evidence)
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
                    (c for c in still_ambiguous if c.golden_record_id == llm_target), None
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
            best = max(still_ambiguous, key=lambda c: c.combined_score)
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

    # ── POST /re-evaluate ───────────────────────────────────

    async def re_evaluate(self, request: ReEvaluationRequest) -> ReEvaluationResponse:
        """Re-evaluate a golden record after enrichment.

        When a merge adds new bucket keys, check if other GRs in those
        buckets should also be merged.

        v4: Uses MCP tools (describe_entity, find_candidates, compare_fields,
            merge_golden_records) instead of direct MySQL access.
        """
        start = time.time()
        chain: list[EvaluationStep] = []
        merges = []
        reviews = []

        # Step 1: Get golden record profile via MCP
        entity_result = await self._mcp.call_tool("describe_entity", {
            "entity_id": request.golden_record_id,
        })
        if entity_result.get("error") or not entity_result.get("entity"):
            return ReEvaluationResponse(
                golden_record_id=request.golden_record_id,
                evaluation_chain=[EvaluationStep(
                    step="error", tool_called="mcp:describe_entity",
                    details={"error": entity_result.get("error", "Entity not found")},
                )],
            )

        # Build persona from entity profile
        persona = self._build_persona_from_entity(entity_result["entity"])

        # Step 2: Find candidates via MCP (includes new bucket key matches)
        cand_result = await self._mcp.call_tool("find_candidates", {
            "orphan_persona": persona.model_dump(),
        })
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
            cmp_dict = await self._mcp.call_tool("compare_fields", {
                "orphan_persona": persona.model_dump(),
                "candidate": cand,
            })
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

            # Above merge threshold and chain_depth allows
            if (comparison.composite > self._cfg.thresholds.auto_merge
                    and request.chain_depth < self._cfg.re_evaluation.force_review_at_depth):
                result = await self._mcp.call_tool("merge_golden_records", {
                    "survivor_id": request.golden_record_id,
                    "absorbed_id": cand_id,
                    "merge_reasoning": {"confidence": comparison.composite},
                })
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

    # ── Internal actions ────────────────────────────────────

    async def _merge(
        self, request, persona, candidate, chain, llm_calls, embedding_calls, start,
    ) -> ResolutionResponse:
        """Execute a merge via MCP and log it."""
        t = time.time()
        merge_result = await self._mcp.call_tool("merge_into_golden_record", {
            "orphan_record_id": request.record_id,
            "orphan_persona": persona.model_dump() if hasattr(persona, "model_dump") else persona,
            "golden_record_id": candidate.golden_record_id,
            "merge_reasoning": {
                "trigger": f"AI_AGENT_{candidate.match_level.value}",
                "confidence": candidate.combined_score,
                "dimension_scores": _extract_dim_scores(candidate).__dict__,
            },
            "company_id": str(request.company_id) if request.company_id is not None else None,
            "record_type": request.record_type,
        })
        chain.append(EvaluationStep(
            step="merge", tool_called="mcp:merge_into_golden_record",
            candidate=candidate.golden_record_id,
            score=candidate.combined_score,
            duration_ms=merge_result.get("duration_ms", int((time.time() - t) * 1000)),
        ))

        dim_scores = _extract_dim_scores(candidate)
        total_ms = int((time.time() - start) * 1000)

        await self._mcp.call_tool("log_decision", {
            "event_id": request.event_id,
            "record_id": request.record_id,
            "decision": "MERGE",
            "target_golden_record_id": candidate.golden_record_id,
            "confidence": candidate.combined_score,
            "dimension_scores": dim_scores.__dict__ if isinstance(dim_scores, DimensionScores) else dim_scores,
            "reasoning": f"Merged into {candidate.canonical_name} via {candidate.match_level.value}",
            "key_factors": _build_key_factors(candidate),
            "evaluation_chain": [s.model_dump() for s in chain],
            "agent_metadata": {
                "trigger_type": f"AI_AGENT_{candidate.match_level.value}",
                "total_duration_ms": total_ms,
                "llm_calls": llm_calls,
                "embedding_calls": embedding_calls,
                "candidates_evaluated": len([s for s in chain if s.step == "compare_fields"]),
            },
        })

        total_ms = int((time.time() - start) * 1000)
        telemetry.record_resolution_duration(total_ms, "MERGE", candidate.match_level.value)

        return ResolutionResponse(
            event_id=request.event_id,
            decision=Decision.MERGE,
            target_golden_record_id=candidate.golden_record_id,
            confidence=candidate.combined_score,
            dimension_scores=dim_scores,
            reasoning=f"Merged into {candidate.canonical_name} ({candidate.match_level.value})",
            key_factors=_build_key_factors(candidate),
            evaluation_chain=chain,
            agent_metadata={
                "total_duration_ms": total_ms,
                "llm_calls": llm_calls,
                "embedding_calls": embedding_calls,
                "candidates_evaluated": len([s for s in chain if s.step == "compare_fields"]),
            },
        )

    async def _create_new(
        self, request, persona, chain, llm_calls, embedding_calls, start, reason="",
    ) -> ResolutionResponse:
        """Create a new golden record via MCP and log it."""
        t = time.time()
        create_result = await self._mcp.call_tool("create_golden_record", {
            "orphan_record_id": request.record_id,
            "orphan_persona": persona.model_dump() if hasattr(persona, "model_dump") else persona,
            "creation_reasoning": {"trigger": "AI_AGENT_NEW", "reasoning": reason},
            "company_id": str(request.company_id) if request.company_id is not None else None,
            "record_type": request.record_type,
        })
        chain.append(EvaluationStep(
            step="create", tool_called="mcp:create_golden_record",
            duration_ms=create_result.get("duration_ms", int((time.time() - t) * 1000)),
            details={"golden_record_id": create_result.get("golden_record_id")},
        ))

        total_ms = int((time.time() - start) * 1000)
        telemetry.record_resolution_duration(total_ms, "NEW_ENTITY")

        await self._mcp.call_tool("log_decision", {
            "event_id": request.event_id,
            "record_id": request.record_id,
            "decision": "NEW_ENTITY",
            "target_golden_record_id": None,
            "confidence": 0.0,
            "dimension_scores": {},
            "reasoning": reason,
            "key_factors": ["no_match"],
            "evaluation_chain": [s.model_dump() for s in chain],
            "agent_metadata": {
                "trigger_type": "AI_AGENT_NEW",
                "total_duration_ms": total_ms,
                "llm_calls": llm_calls,
                "embedding_calls": embedding_calls,
                "candidates_evaluated": len([s for s in chain if s.step == "compare_fields"]),
            },
        })

        return ResolutionResponse(
            event_id=request.event_id,
            decision=Decision.NEW_ENTITY,
            target_golden_record_id=create_result.get("golden_record_id"),
            confidence=0.0,
            reasoning=reason,
            key_factors=["no_match"],
            evaluation_chain=chain,
            agent_metadata={
                "total_duration_ms": total_ms,
                "llm_calls": llm_calls,
                "embedding_calls": embedding_calls,
            },
        )

    async def _submit_review(
        self, request, persona, candidate, chain, llm_calls, embedding_calls, start,
        reason="", key_uncertainty="", forced=False,
    ) -> ResolutionResponse:
        """Submit to human review via MCP and log it."""
        t = time.time()
        review_result = await self._mcp.call_tool("submit_for_review", {
            "orphan_record_id": request.record_id,
            "orphan_persona": persona.model_dump() if hasattr(persona, "model_dump") else persona,
            "candidate_golden_record_id": candidate.golden_record_id,
            "review_reasoning": {
                "confidence": candidate.combined_score,
                "dimension_scores": _extract_dim_scores(candidate).__dict__,
                "reasoning": reason,
                "key_uncertainty": key_uncertainty,
                "trigger_type": "AI_AGENT_LLM" if llm_calls > 0 else "AI_AGENT_EMBEDDING",
            },
            "company_id": str(request.company_id) if request.company_id is not None else None,
            "record_type": request.record_type,
        })
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

        await self._mcp.call_tool("log_decision", {
            "event_id": request.event_id,
            "record_id": request.record_id,
            "decision": "REVIEW",
            "target_golden_record_id": candidate.golden_record_id,
            "confidence": candidate.combined_score,
            "dimension_scores": dim_scores.__dict__ if isinstance(dim_scores, DimensionScores) else dim_scores,
            "reasoning": reason,
            "key_factors": _build_key_factors(candidate) + (["cascade_guard"] if forced else []),
            "evaluation_chain": [s.model_dump() for s in chain],
            "agent_metadata": {
                "trigger_type": "AI_AGENT_LLM" if llm_calls > 0 else "AI_AGENT_EMBEDDING",
                "total_duration_ms": total_ms,
                "llm_calls": llm_calls,
                "embedding_calls": embedding_calls,
                "candidates_evaluated": len([s for s in chain if s.step == "compare_fields"]),
            },
        })

        return ResolutionResponse(
            event_id=request.event_id,
            decision=Decision.REVIEW,
            target_golden_record_id=candidate.golden_record_id,
            confidence=candidate.combined_score,
            dimension_scores=dim_scores,
            reasoning=reason,
            key_factors=_build_key_factors(candidate),
            evaluation_chain=chain,
            agent_metadata={
                "total_duration_ms": total_ms,
                "llm_calls": llm_calls,
                "embedding_calls": embedding_calls,
            },
        )

    # ── Helpers ─────────────────────────────────────────────

    def _build_llm_evidence(
        self, persona: ClassifiedPersona, candidates: list[CandidateMatch], chain: list
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

    def _build_persona_from_entity(self, entity: dict) -> ClassifiedPersona:
        """Reconstruct ClassifiedPersona from describe_entity response."""
        from models.persona import (
            IdentityDimension, IndustryDimension, LocationDimension,
            CommodityDimension, BehavioralDimension,
        )
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


# ── Utility functions ───────────────────────────────────────

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
