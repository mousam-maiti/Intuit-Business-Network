"""Tests for Pydantic models — persona, audit, resolution."""
import pytest
from datetime import datetime, timezone
from models.persona import (
    IdentityDimension, IndustryDimension, LocationDimension,
    CommodityDimension, BehavioralDimension, SparsityScores,
    ClassifiedPersona, GoldenRecord,
)
from models.audit import AuditRecord, PendingResolution
from models.resolution import (
    Decision, MatchLevel, DimensionConfidence, FieldMatchResult,
    ResolutionRequest, DimensionResult, ComparisonResult,
    SimilarityResult, CandidateMatch, EvaluationStep,
    DimensionScores, ResolutionResponse, ReEvaluationResponse,
)


# ── Persona models ──────────────────────────────────────────

class TestIdentityDimension:
    def test_defaults(self):
        d = IdentityDimension()
        assert d.normalized_name == ""
        assert d.name_tokens == []
        assert d.ein_clean is None
        assert d.phone_digits is None
        assert d.email is None

    def test_populate_by_name_alias(self):
        """canonical_name alias should populate normalized_name."""
        d = IdentityDimension(canonical_name="Test Corp")
        assert d.normalized_name == "Test Corp"

    def test_direct_field(self):
        d = IdentityDimension(normalized_name="Test Corp")
        assert d.normalized_name == "Test Corp"


class TestIndustryDimension:
    def test_defaults(self):
        d = IndustryDimension()
        assert d.naics_code is None
        assert d.commodity_keywords == []

    def test_full(self):
        d = IndustryDimension(
            naics_code="238220",
            naics_sector="23",
            naics_subsector="238",
            commodity_keywords=["pipe"],
        )
        assert d.naics_code == "238220"
        assert d.commodity_keywords == ["pipe"]


class TestLocationDimension:
    def test_defaults(self):
        d = LocationDimension()
        assert d.state == ""
        assert d.city_norm is None

    def test_full(self):
        d = LocationDimension(state="TX", city_norm="AUSTIN", zip3="787", zip5="78704")
        assert d.zip5 == "78704"


class TestCommodityDimension:
    def test_defaults(self):
        d = CommodityDimension()
        assert d.top_keywords == []
        assert d.service_categories == []


class TestBehavioralDimension:
    def test_defaults(self):
        d = BehavioralDimension()
        assert d.volume_bracket is None
        assert d.avg_transaction is None

    def test_full(self):
        d = BehavioralDimension(volume_bracket="HIGH", avg_transaction=500.0, transaction_count=100)
        assert d.transaction_count == 100


class TestClassifiedPersona:
    def test_defaults(self):
        p = ClassifiedPersona()
        assert isinstance(p.identity, IdentityDimension)
        assert isinstance(p.industry, IndustryDimension)
        assert isinstance(p.location, LocationDimension)
        assert isinstance(p.commodity, CommodityDimension)
        assert isinstance(p.behavioral, BehavioralDimension)
        assert isinstance(p.sparsity, SparsityScores)

    def test_model_dump_roundtrip(self):
        p = ClassifiedPersona(
            identity=IdentityDimension(normalized_name="Test"),
            location=LocationDimension(state="TX"),
        )
        d = p.model_dump()
        p2 = ClassifiedPersona.model_validate(d)
        assert p2.identity.normalized_name == "Test"
        assert p2.location.state == "TX"


class TestGoldenRecord:
    def test_defaults(self):
        gr = GoldenRecord(golden_record_id="G-001", canonical_name="Test")
        assert gr.source_count == 1
        assert gr.confidence == 0.5
        assert gr.status == "ACTIVE"
        assert gr.entity_type == "PHANTOM"
        assert gr.name_variants == []
        assert gr.source_records == []
        assert gr.bucket_keys == []

    def test_full(self):
        gr = GoldenRecord(
            golden_record_id="G-001",
            canonical_name="Test Corp",
            name_variants=["Test Corp", "Test"],
            source_count=5,
            confidence=0.92,
            status="ACTIVE",
            entity_type="QB_USER",
            source_records=["R-1", "R-2"],
        )
        assert gr.source_count == 5
        assert len(gr.name_variants) == 2

    def test_model_dump_roundtrip(self):
        gr = GoldenRecord(golden_record_id="G-001", canonical_name="Test")
        d = gr.model_dump()
        gr2 = GoldenRecord.model_validate(d)
        assert gr2.golden_record_id == "G-001"


# ── Audit models ────────────────────────────────────────────

class TestAuditRecord:
    def test_defaults(self):
        a = AuditRecord(
            audit_id="A-001",
            event_id="EVT-001",
            record_id="R-001",
            decision="MERGE",
        )
        assert a.perspective == "GLOBAL"
        assert a.confidence == 0.0
        assert a.dimension_scores == {}
        assert a.key_factors == []
        assert a.evaluation_chain == []
        assert a.created_at  # should be auto-generated

    def test_created_at_is_iso_format(self):
        a = AuditRecord(audit_id="A-001", event_id="E-1", record_id="R-1", decision="MERGE")
        # Should be parseable as ISO datetime
        dt = datetime.fromisoformat(a.created_at)
        assert dt is not None

    def test_full(self):
        a = AuditRecord(
            audit_id="A-001",
            event_id="EVT-001",
            record_id="R-001",
            decision="MERGE",
            trigger_type="AI_AGENT",
            target_golden_id="G-001",
            confidence=0.92,
            dimension_scores={"identity": 0.95},
            reasoning="High confidence match",
            key_factors=["EIN exact"],
        )
        assert a.trigger_type == "AI_AGENT"
        assert a.confidence == 0.92


class TestPendingResolution:
    def test_defaults(self):
        p = PendingResolution(
            match_id="PR-001",
            orphan_golden_id="G-001",
            candidate_golden_id="G-002",
        )
        assert p.status == "PENDING"
        assert p.confidence == 0.0
        assert p.decided_by is None
        assert p.created_at

    def test_full(self):
        p = PendingResolution(
            match_id="PR-001",
            orphan_golden_id="G-001",
            candidate_golden_id="G-002",
            confidence=0.72,
            reasoning="Ambiguous match",
            key_uncertainty="Name similarity low",
            status="PENDING",
        )
        assert p.key_uncertainty == "Name similarity low"


# ── Resolution models ───────────────────────────────────────

class TestEnums:
    def test_decision_values(self):
        assert Decision.MERGE.value == "MERGE"
        assert Decision.NEW_ENTITY.value == "NEW_ENTITY"
        assert Decision.REVIEW.value == "REVIEW"
        assert Decision.NO_MERGE_FOUND.value == "NO_MERGE_FOUND"

    def test_match_level_values(self):
        assert MatchLevel.EXACT.value == "EXACT"
        assert MatchLevel.DETERMINISTIC.value == "DETERMINISTIC"
        assert MatchLevel.EMBEDDING.value == "EMBEDDING"
        assert MatchLevel.LLM.value == "LLM"
        assert MatchLevel.NONE.value == "NONE"

    def test_dimension_confidence_values(self):
        assert DimensionConfidence.HIGH.value == "HIGH"
        assert DimensionConfidence.MEDIUM.value == "MEDIUM"
        assert DimensionConfidence.LOW.value == "LOW"
        assert DimensionConfidence.INSUFFICIENT.value == "INSUFFICIENT"

    def test_field_match_result_values(self):
        assert FieldMatchResult.EXACT.value == "EXACT"
        assert FieldMatchResult.PARTIAL.value == "PARTIAL"
        assert FieldMatchResult.DOMAIN_MATCH.value == "DOMAIN_MATCH"
        assert FieldMatchResult.MISSING.value == "MISSING"
        assert FieldMatchResult.MISMATCH.value == "MISMATCH"


class TestDimensionResult:
    def test_defaults(self):
        d = DimensionResult()
        assert d.score == 0.0
        assert d.confidence == DimensionConfidence.INSUFFICIENT
        assert d.details == {}


class TestComparisonResult:
    def test_defaults(self):
        c = ComparisonResult()
        assert c.composite == 0.0
        assert c.disqualified is False
        assert c.disqualification_reason is None

    def test_model_dump(self):
        c = ComparisonResult(disqualified=True, disqualification_reason="EIN")
        d = c.model_dump()
        assert d["disqualified"] is True
        assert d["disqualification_reason"] == "EIN"


class TestSimilarityResult:
    def test_defaults(self):
        s = SimilarityResult()
        assert s.composite_similarity == 0.0
        assert s.model_used == ""


class TestCandidateMatch:
    def test_defaults(self):
        c = CandidateMatch(golden_record_id="G-001", canonical_name="Test")
        assert c.combined_score == 0.0
        assert c.match_level == MatchLevel.NONE
        assert c.disqualified is False


class TestEvaluationStep:
    def test_defaults(self):
        e = EvaluationStep(step="find_candidates")
        assert e.tool_called == ""
        assert e.candidate is None
        assert e.details == {}


class TestResolutionRequest:
    def test_creation(self):
        r = ResolutionRequest(
            event_id="E-001",
            record_id="R-001",
            classified_persona=ClassifiedPersona(),
        )
        assert r.record_type == "vendor"
        assert r.chain_depth == 0


class TestResolutionResponse:
    def test_creation(self):
        r = ResolutionResponse(event_id="E-001", decision=Decision.MERGE)
        assert r.confidence == 0.0
        assert r.key_factors == []
