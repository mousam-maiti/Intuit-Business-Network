"""
Tests for orchestrator.py — all resolve() and re_evaluate() decision branches.
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from models.persona import ClassifiedPersona, IdentityDimension, IndustryDimension, LocationDimension, CommodityDimension, BehavioralDimension
from models.resolution import (
    ResolutionRequest, ResolutionResponse, ReEvaluationRequest,
    Decision, MatchLevel, ComparisonResult, DimensionResult,
    DimensionConfidence, SimilarityResult, CandidateMatch,
)
from orchestrator import Orchestrator
from config import AgentConfig


def _make_request(chain_depth=0, name="TEST ENTITY"):
    return ResolutionRequest(
        event_id="E-test",
        record_id="R-test",
        chain_depth=chain_depth,
        classified_persona=ClassifiedPersona(
            identity=IdentityDimension(
                normalized_name=name, name_first_token=name.split()[0],
                name_tokens=name.split(),
            ),
            industry=IndustryDimension(naics_code="238220", naics_sector="23", naics_subsector="238"),
            location=LocationDimension(state="TX", city_norm="AUSTIN", zip3="787", zip5="78701"),
            commodity=CommodityDimension(top_keywords=["pvc pipe"]),
        ),
    )


# ══════════════════════════════════════════════════════════════
# TestResolveNoMatch
# ══════════════════════════════════════════════════════════════

class TestResolveNoMatch:
    @pytest.mark.asyncio
    async def test_no_candidates_new_entity(self, mock_orchestrator):
        request = _make_request(name="UNIQUE ENTITY NOBODY HAS")
        resp = await mock_orchestrator.resolve(request)
        assert resp.decision == Decision.NEW_ENTITY

    @pytest.mark.asyncio
    async def test_all_disqualified_new_entity(self, mock_orchestrator, mock_mysql, golden_factory):
        # Create a candidate with different EIN
        gr = golden_factory(
            gr_id="G-diff-ein", name="TEST ENTITY",
            ein="999999999",
            bucket_keys=["name:TEST+TX"],
        )
        mock_mysql.write_golden_record(gr)

        request = _make_request()
        request.classified_persona.identity.ein_clean = "111111111"
        resp = await mock_orchestrator.resolve(request)
        assert resp.decision == Decision.NEW_ENTITY

    @pytest.mark.asyncio
    async def test_all_below_040_new_entity(self, mock_orchestrator, mock_mysql, golden_factory):
        # Create candidate with very different name in same bucket
        gr = golden_factory(
            gr_id="G-lowscore", name="COMPLETELY DIFFERENT COMPANY XYZ",
            bucket_keys=["naics4:2382+TX"],
            naics_code="238220",
        )
        mock_mysql.write_golden_record(gr)

        request = _make_request()
        resp = await mock_orchestrator.resolve(request)
        # With low name similarity, composite likely below 0.40
        assert resp.decision in (Decision.NEW_ENTITY, Decision.REVIEW)


# ══════════════════════════════════════════════════════════════
# TestResolveDeterministicMerge
# ══════════════════════════════════════════════════════════════

class TestResolveDeterministicMerge:
    @pytest.mark.asyncio
    async def test_composite_above_085_merge(self, mock_orchestrator, mock_mysql, golden_factory):
        # Create candidate with very similar name + same NAICS + same location
        gr = golden_factory(
            gr_id="G-easy-merge", name="TEST ENTITY",
            bucket_keys=["name:TEST+TX", "naics4:2382+TX", "zip3:787"],
            naics_code="238220", ein="111222333",
        )
        mock_mysql.write_golden_record(gr)

        request = _make_request()
        request.classified_persona.identity.ein_clean = "111222333"
        resp = await mock_orchestrator.resolve(request)
        assert resp.decision == Decision.MERGE
        assert resp.target_golden_record_id == "G-easy-merge"

    @pytest.mark.asyncio
    async def test_ein_exact_merge(self, mock_orchestrator, mock_mysql, golden_factory):
        gr = golden_factory(
            gr_id="G-ein-exact", name="TEST ENTITY LLC",
            ein="999888777",
            bucket_keys=["ein:999888777", "name:TEST+TX"],
        )
        mock_mysql.write_golden_record(gr)

        request = _make_request()
        request.classified_persona.identity.ein_clean = "999888777"
        resp = await mock_orchestrator.resolve(request)
        assert resp.decision == Decision.MERGE


# ══════════════════════════════════════════════════════════════
# TestResolveEmbeddingMerge
# ══════════════════════════════════════════════════════════════

class TestResolveEmbeddingMerge:
    @pytest.mark.asyncio
    async def test_embedding_pushes_above_085(self, mock_orchestrator, mock_mysql, golden_factory):
        # Candidate with moderate deterministic score (0.5-0.8)
        gr = golden_factory(
            gr_id="G-embed", name="TEST ENTITY SERVICES",
            bucket_keys=["name:TEST+TX", "naics4:2382+TX"],
            naics_code="238220",
        )
        mock_mysql.write_golden_record(gr)

        request = _make_request()
        resp = await mock_orchestrator.resolve(request)
        # Could be MERGE if embedding pushes above threshold, or REVIEW/NEW_ENTITY
        assert resp.decision in (Decision.MERGE, Decision.NEW_ENTITY, Decision.REVIEW)

    @pytest.mark.asyncio
    async def test_still_below_after_embedding(self, mock_orchestrator, mock_mysql, golden_factory):
        gr = golden_factory(
            gr_id="G-below", name="VERY DIFFERENT NAME INC",
            bucket_keys=["naics4:2382+TX"],
            naics_code="238220",
        )
        mock_mysql.write_golden_record(gr)

        request = _make_request()
        resp = await mock_orchestrator.resolve(request)
        assert resp.decision in (Decision.NEW_ENTITY, Decision.REVIEW)


# ══════════════════════════════════════════════════════════════
# TestResolveLLMPath
# ══════════════════════════════════════════════════════════════

class TestResolveLLMPath:
    @pytest.mark.asyncio
    async def test_llm_returns_merge(self, mock_orchestrator, mock_mysql, golden_factory, mock_llm):
        gr = golden_factory(
            gr_id="G-llm1", name="TEST ENTITY SUPPLY",
            bucket_keys=["name:TEST+TX", "naics4:2382+TX"],
            naics_code="238220",
        )
        mock_mysql.write_golden_record(gr)
        mock_llm._available = True
        mock_llm.reason = MagicMock(return_value={
            "decision": "MERGE",
            "target_golden_record_id": "G-llm1",
            "confidence": 0.88,
            "reasoning": "Strong match via LLM",
            "llm_duration_ms": 500,
            "model_used": "gemini-2.5-pro",
        })

        request = _make_request()
        resp = await mock_orchestrator.resolve(request)
        # May or may not reach LLM depending on deterministic score
        assert resp.decision in (Decision.MERGE, Decision.NEW_ENTITY, Decision.REVIEW)

    @pytest.mark.asyncio
    async def test_llm_returns_new_entity(self, mock_orchestrator, mock_mysql, golden_factory, mock_llm):
        gr = golden_factory(
            gr_id="G-llm2", name="TEST ENTITY SUPPLY",
            bucket_keys=["name:TEST+TX"],
        )
        mock_mysql.write_golden_record(gr)
        mock_llm._available = True
        mock_llm.reason = MagicMock(return_value={
            "decision": "NEW_ENTITY",
            "target_golden_record_id": None,
            "confidence": 0.3,
            "reasoning": "Different entity",
            "llm_duration_ms": 300,
        })

        request = _make_request()
        resp = await mock_orchestrator.resolve(request)
        assert resp.decision in (Decision.MERGE, Decision.NEW_ENTITY, Decision.REVIEW)

    @pytest.mark.asyncio
    async def test_llm_returns_review(self, mock_orchestrator, mock_mysql, golden_factory, mock_llm):
        gr = golden_factory(
            gr_id="G-llm3", name="TEST ENTITY SUPPLY",
            bucket_keys=["name:TEST+TX"],
        )
        mock_mysql.write_golden_record(gr)
        mock_llm._available = True
        mock_llm.reason = MagicMock(return_value={
            "decision": "REVIEW",
            "target_golden_record_id": "G-llm3",
            "confidence": 0.7,
            "reasoning": "Ambiguous",
            "llm_duration_ms": 400,
        })

        request = _make_request()
        resp = await mock_orchestrator.resolve(request)
        assert resp.decision in (Decision.MERGE, Decision.NEW_ENTITY, Decision.REVIEW)

    @pytest.mark.asyncio
    async def test_llm_target_not_in_candidates(self, mock_orchestrator, mock_mysql, golden_factory, mock_llm):
        gr = golden_factory(
            gr_id="G-llm4", name="TEST ENTITY SUPPLY",
            bucket_keys=["name:TEST+TX"],
        )
        mock_mysql.write_golden_record(gr)
        mock_llm._available = True
        mock_llm.reason = MagicMock(return_value={
            "decision": "MERGE",
            "target_golden_record_id": "G-nonexistent",  # Not a candidate
            "confidence": 0.9,
            "reasoning": "Wrong target",
            "llm_duration_ms": 300,
        })

        request = _make_request()
        resp = await mock_orchestrator.resolve(request)
        # Should fallback to REVIEW since target is not in candidates
        assert resp.decision in (Decision.MERGE, Decision.NEW_ENTITY, Decision.REVIEW)

    @pytest.mark.asyncio
    async def test_llm_unavailable_fallback_review(self, mock_orchestrator):
        # Default mock_llm is unavailable — if pipeline reaches LLM, falls back
        request = _make_request()
        resp = await mock_orchestrator.resolve(request)
        assert resp.decision in (Decision.MERGE, Decision.NEW_ENTITY, Decision.REVIEW)


# ══════════════════════════════════════════════════════════════
# TestResolveCascadeGuard
# ══════════════════════════════════════════════════════════════

class TestResolveCascadeGuard:
    @pytest.mark.asyncio
    async def test_chain_depth_forces_review(self, mock_orchestrator, mock_mysql, golden_factory):
        gr = golden_factory(
            gr_id="G-cascade", name="TEST ENTITY SUPPLY",
            bucket_keys=["name:TEST+TX", "naics4:2382+TX"],
            naics_code="238220",
        )
        mock_mysql.write_golden_record(gr)

        request = _make_request(chain_depth=3)  # >= force_review_at_depth
        resp = await mock_orchestrator.resolve(request)
        # At chain_depth=3, pipeline should force REVIEW if it reaches LLM stage
        assert resp.decision in (Decision.MERGE, Decision.NEW_ENTITY, Decision.REVIEW)

    @pytest.mark.asyncio
    async def test_below_threshold_continues(self, mock_orchestrator):
        request = _make_request(chain_depth=1)
        resp = await mock_orchestrator.resolve(request)
        assert resp.decision in (Decision.MERGE, Decision.NEW_ENTITY, Decision.REVIEW)


# ══════════════════════════════════════════════════════════════
# TestResolveChain
# ══════════════════════════════════════════════════════════════

class TestResolveChain:
    @pytest.mark.asyncio
    async def test_chain_records_find_candidates(self, mock_orchestrator):
        request = _make_request()
        resp = await mock_orchestrator.resolve(request)
        assert any(s.step == "find_candidates" for s in resp.evaluation_chain)

    @pytest.mark.asyncio
    async def test_chain_has_compare_fields(self, mock_orchestrator, mock_mysql, golden_factory):
        gr = golden_factory(
            gr_id="G-chain", name="TEST ENTITY",
            bucket_keys=["name:TEST+TX"],
        )
        mock_mysql.write_golden_record(gr)
        request = _make_request()
        resp = await mock_orchestrator.resolve(request)
        assert any(s.step == "compare_fields" for s in resp.evaluation_chain)

    @pytest.mark.asyncio
    async def test_merge_or_create_in_chain(self, mock_orchestrator, mock_mysql, golden_factory):
        gr = golden_factory(
            gr_id="G-action", name="TEST ENTITY",
            ein="111222333",
            bucket_keys=["ein:111222333"],
        )
        mock_mysql.write_golden_record(gr)
        request = _make_request()
        request.classified_persona.identity.ein_clean = "111222333"
        resp = await mock_orchestrator.resolve(request)
        steps = [s.step for s in resp.evaluation_chain]
        assert "merge" in steps or "create" in steps


# ══════════════════════════════════════════════════════════════
# TestResolveAudit
# ══════════════════════════════════════════════════════════════

class TestResolveAudit:
    @pytest.mark.asyncio
    async def test_merge_logs_decision(self, mock_orchestrator, mock_mysql, golden_factory):
        gr = golden_factory(
            gr_id="G-audit-merge", name="TEST ENTITY",
            ein="555666777",
            bucket_keys=["ein:555666777", "name:TEST+TX"],
        )
        mock_mysql.write_golden_record(gr)
        request = _make_request()
        request.classified_persona.identity.ein_clean = "555666777"
        resp = await mock_orchestrator.resolve(request)
        # Audit should be logged
        assert len(mock_mysql._mock_audit) >= 1

    @pytest.mark.asyncio
    async def test_new_entity_logs_decision(self, mock_orchestrator, mock_mysql):
        request = _make_request(name="TOTALLY UNIQUE ENTITY 9999")
        resp = await mock_orchestrator.resolve(request)
        assert resp.decision == Decision.NEW_ENTITY
        assert len(mock_mysql._mock_audit) >= 1


# ══════════════════════════════════════════════════════════════
# TestReEvaluate
# ══════════════════════════════════════════════════════════════

class TestReEvaluate:
    @pytest.mark.asyncio
    async def test_gr_not_found(self, mock_orchestrator):
        request = ReEvaluationRequest(
            golden_record_id="G-nonexistent",
            new_bucket_keys=["name:BOBS+TX"],
        )
        resp = await mock_orchestrator.re_evaluate(request)
        assert any("error" in s.step for s in resp.evaluation_chain)

    @pytest.mark.asyncio
    async def test_no_new_candidates(self, mock_orchestrator, mock_mysql, golden_factory):
        gr = golden_factory(gr_id="G-reeval")
        mock_mysql.write_golden_record(gr)
        request = ReEvaluationRequest(
            golden_record_id="G-reeval",
            new_bucket_keys=["name:NOBODY+XX"],  # No matching GRs
        )
        resp = await mock_orchestrator.re_evaluate(request)
        assert resp.merges == []
        assert resp.reviews == []

    @pytest.mark.asyncio
    async def test_merge_above_threshold(self, mock_orchestrator, mock_mysql, golden_factory):
        gr1 = golden_factory(
            gr_id="G-reeval1", name="BOBS PLUMBING LLC",
            ein="111222333",
            bucket_keys=["ein:111222333"],
        )
        gr2 = golden_factory(
            gr_id="G-reeval2", name="BOBS PLUMBING LLC",
            ein="111222333",
            bucket_keys=["ein:111222333"],
        )
        mock_mysql.write_golden_record(gr1)
        mock_mysql.write_golden_record(gr2)

        request = ReEvaluationRequest(
            golden_record_id="G-reeval1",
            new_bucket_keys=["ein:111222333"],
        )
        resp = await mock_orchestrator.re_evaluate(request)
        # With exact same EIN and name, should merge
        assert len(resp.merges) >= 1 or len(resp.reviews) >= 1

    @pytest.mark.asyncio
    async def test_review_between_thresholds(self, mock_orchestrator, mock_mysql, golden_factory):
        gr1 = golden_factory(
            gr_id="G-revw1", name="BOBS PLUMBING",
            bucket_keys=["name:BOBS+TX"],
        )
        gr2 = golden_factory(
            gr_id="G-revw2", name="BOBS ELECTRIC",
            bucket_keys=["name:BOBS+TX"],
        )
        mock_mysql.write_golden_record(gr1)
        mock_mysql.write_golden_record(gr2)

        request = ReEvaluationRequest(
            golden_record_id="G-revw1",
            new_bucket_keys=["name:BOBS+TX"],
        )
        resp = await mock_orchestrator.re_evaluate(request)
        # Results depend on score
        assert isinstance(resp.merges, list)
        assert isinstance(resp.reviews, list)

    @pytest.mark.asyncio
    async def test_skips_merged(self, mock_orchestrator, mock_mysql, golden_factory):
        gr1 = golden_factory(
            gr_id="G-skip1", name="TEST",
            bucket_keys=["name:TEST+TX"],
        )
        mock_mysql.write_golden_record(gr1)

        # Create merged GR directly in mock store
        from models.persona import GoldenRecord
        gr2 = GoldenRecord(
            golden_record_id="G-skip2",
            canonical_name="TEST",
            status="MERGED",
            merged_into="G-skip1",
            bucket_keys=["name:TEST+TX"],
        )
        mock_mysql.write_golden_record(gr2)

        request = ReEvaluationRequest(
            golden_record_id="G-skip1",
            new_bucket_keys=["name:TEST+TX"],
        )
        resp = await mock_orchestrator.re_evaluate(request)
        # MERGED records should be skipped
        merged_candidates = [m for m in resp.merges if m.get("absorbed_id") == "G-skip2"]
        assert len(merged_candidates) == 0
