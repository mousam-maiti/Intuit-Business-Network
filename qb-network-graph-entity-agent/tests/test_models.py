"""
Tests for models/ — persona.py, resolution.py, audit.py.
"""
import pytest
from models.persona import (
    IdentityDimension, IndustryDimension, LocationDimension,
    CommodityDimension, BehavioralDimension, SparsityScores,
    ClassifiedPersona, GoldenRecord,
)
from models.resolution import (
    Decision, MatchLevel, DimensionConfidence, FieldMatchResult,
    ResolutionRequest, ResolutionResponse, ReEvaluationRequest,
    ReEvaluationResponse, ComparisonResult, SimilarityResult,
    DimensionResult, CandidateMatch, DimensionScores, EvaluationStep,
)
from models.audit import AuditRecord, PendingResolution


# ══════════════════════════════════════════════════════════════
# TestIdentityDimension
# ══════════════════════════════════════════════════════════════

class TestIdentityDimension:
    def test_canonical_name_alias(self):
        """canonical_name alias should populate normalized_name."""
        dim = IdentityDimension(canonical_name="BOB'S PLUMBING")
        assert dim.normalized_name == "BOB'S PLUMBING"

    def test_populate_by_name(self):
        """Both alias and field name should work."""
        dim = IdentityDimension(normalized_name="DIRECT")
        assert dim.normalized_name == "DIRECT"

    def test_defaults(self):
        dim = IdentityDimension()
        assert dim.normalized_name == ""
        assert dim.name_first_token == ""
        assert dim.name_tokens == []
        assert dim.ein_clean is None
        assert dim.phone_digits is None


# ══════════════════════════════════════════════════════════════
# TestClassifiedPersona
# ══════════════════════════════════════════════════════════════

class TestClassifiedPersona:
    def test_default_construction(self):
        p = ClassifiedPersona()
        assert isinstance(p.identity, IdentityDimension)
        assert isinstance(p.industry, IndustryDimension)
        assert isinstance(p.location, LocationDimension)
        assert isinstance(p.commodity, CommodityDimension)
        assert isinstance(p.behavioral, BehavioralDimension)

    def test_model_validate_from_dict(self):
        data = {
            "identity": {"normalized_name": "TEST CORP", "ein_clean": "123456789"},
            "location": {"state": "CA"},
        }
        p = ClassifiedPersona.model_validate(data)
        assert p.identity.normalized_name == "TEST CORP"
        assert p.identity.ein_clean == "123456789"
        assert p.location.state == "CA"

    def test_model_dump_roundtrip(self):
        p = ClassifiedPersona(
            identity=IdentityDimension(normalized_name="ROUNDTRIP"),
            location=LocationDimension(state="NY"),
        )
        d = p.model_dump()
        p2 = ClassifiedPersona.model_validate(d)
        assert p2.identity.normalized_name == "ROUNDTRIP"
        assert p2.location.state == "NY"

    def test_sparse_persona(self):
        """Persona with only a name should still be valid."""
        p = ClassifiedPersona(
            identity=IdentityDimension(normalized_name="SPARSE LLC"),
        )
        assert p.identity.normalized_name == "SPARSE LLC"
        assert p.industry.naics_code is None
        assert p.location.state == ""


# ══════════════════════════════════════════════════════════════
# TestGoldenRecord
# ══════════════════════════════════════════════════════════════

class TestGoldenRecord:
    def test_required_fields(self):
        gr = GoldenRecord(golden_record_id="G-001", canonical_name="Test")
        assert gr.golden_record_id == "G-001"
        assert gr.canonical_name == "Test"

    def test_status_defaults(self):
        gr = GoldenRecord(golden_record_id="G-002", canonical_name="Test")
        assert gr.status == "ACTIVE"
        assert gr.entity_type == "PHANTOM"
        assert gr.confidence == 0.5
        assert gr.source_count == 1

    def test_model_dump_includes_nested_persona(self):
        gr = GoldenRecord(
            golden_record_id="G-003",
            canonical_name="Nested Test",
            persona=ClassifiedPersona(
                identity=IdentityDimension(normalized_name="NESTED"),
            ),
        )
        d = gr.model_dump()
        assert d["persona"]["identity"]["normalized_name"] == "NESTED"

    def test_merged_into(self):
        gr = GoldenRecord(
            golden_record_id="G-absorbed",
            canonical_name="Absorbed",
            status="MERGED",
            merged_into="G-survivor",
        )
        assert gr.status == "MERGED"
        assert gr.merged_into == "G-survivor"


# ══════════════════════════════════════════════════════════════
# TestEnums
# ══════════════════════════════════════════════════════════════

class TestEnums:
    def test_decision_enum_values(self):
        assert Decision.MERGE.value == "MERGE"
        assert Decision.NEW_ENTITY.value == "NEW_ENTITY"
        assert Decision.REVIEW.value == "REVIEW"
        assert Decision.NO_MERGE_FOUND.value == "NO_MERGE_FOUND"

    def test_match_level_string_comparison(self):
        assert MatchLevel.DETERMINISTIC == "DETERMINISTIC"
        assert MatchLevel.EMBEDDING == "EMBEDDING"
        assert MatchLevel.LLM == "LLM"
        assert MatchLevel.EXACT == "EXACT"
        assert MatchLevel.NONE == "NONE"


# ══════════════════════════════════════════════════════════════
# TestResolutionModels
# ══════════════════════════════════════════════════════════════

class TestResolutionModels:
    def test_resolution_request_construction(self):
        req = ResolutionRequest(
            event_id="E-001",
            record_id="R-001",
            classified_persona=ClassifiedPersona(),
        )
        assert req.event_id == "E-001"
        assert req.record_id == "R-001"
        assert req.record_type == "vendor"
        assert req.chain_depth == 0

    def test_resolution_response_defaults(self):
        resp = ResolutionResponse(
            event_id="E-001",
            decision=Decision.MERGE,
        )
        assert resp.confidence == 0.0
        assert resp.reasoning == ""
        assert resp.key_factors == []
        assert resp.evaluation_chain == []

    def test_resolution_request_defaults(self):
        req = ResolutionRequest(
            event_id="E-002",
            record_id="R-002",
            classified_persona=ClassifiedPersona(),
        )
        assert req.chain_depth == 0
        assert req.record_type == "vendor"

    def test_resolution_response_construction(self):
        resp = ResolutionResponse(
            event_id="E-003",
            decision=Decision.NEW_ENTITY,
            target_golden_record_id="G-123",
            confidence=0.95,
            reasoning="Test reasoning",
        )
        assert resp.target_golden_record_id == "G-123"
        assert resp.confidence == 0.95


# ══════════════════════════════════════════════════════════════
# TestReEvaluationModels
# ══════════════════════════════════════════════════════════════

class TestReEvaluationModels:
    def test_re_evaluation_request_construction(self):
        req = ReEvaluationRequest(
            golden_record_id="G-001",
            new_bucket_keys=["name:BOBS+TX"],
        )
        assert req.golden_record_id == "G-001"
        assert len(req.new_bucket_keys) == 1

    def test_chain_depth_default(self):
        req = ReEvaluationRequest(golden_record_id="G-002")
        assert req.chain_depth == 1


# ══════════════════════════════════════════════════════════════
# TestComparisonResult
# ══════════════════════════════════════════════════════════════

class TestComparisonResult:
    def test_disqualified_result(self):
        cr = ComparisonResult(
            disqualified=True,
            disqualification_reason="Different EIN",
        )
        assert cr.disqualified is True
        assert cr.disqualification_reason == "Different EIN"
        assert cr.composite == 0.0

    def test_normal_result_with_all_dimensions(self):
        cr = ComparisonResult(
            identity=DimensionResult(score=0.9, confidence=DimensionConfidence.HIGH),
            industry=DimensionResult(score=0.8, confidence=DimensionConfidence.HIGH),
            location=DimensionResult(score=0.7, confidence=DimensionConfidence.MEDIUM),
            commodity=DimensionResult(score=0.6, confidence=DimensionConfidence.MEDIUM),
            behavioral=DimensionResult(score=0.5, confidence=DimensionConfidence.LOW),
            composite=0.75,
            weights_used={"identity": 0.35},
        )
        assert cr.composite == 0.75
        assert cr.disqualified is False


# ══════════════════════════════════════════════════════════════
# TestAuditModels
# ══════════════════════════════════════════════════════════════

class TestAuditModels:
    def test_audit_record_construction(self):
        ar = AuditRecord(
            audit_id="A-001",
            event_id="E-001",
            record_id="R-001",
            decision="MERGE",
            confidence=0.92,
        )
        assert ar.audit_id == "A-001"
        assert ar.decision == "MERGE"
        assert ar.perspective == "GLOBAL"
        assert ar.created_at  # auto-generated

    def test_pending_resolution_status_default(self):
        pr = PendingResolution(
            match_id="PR-001",
            orphan_golden_id="G-orphan",
            candidate_golden_id="G-cand",
        )
        assert pr.status == "PENDING"
        assert pr.confidence == 0.0

    def test_audit_record_defaults(self):
        ar = AuditRecord(
            audit_id="A-002",
            event_id="E-002",
            record_id="R-002",
            decision="NEW_ENTITY",
        )
        assert ar.trigger_type == ""
        assert ar.candidates_evaluated == 0
        assert ar.llm_calls == 0
        assert ar.dimension_scores == {}
