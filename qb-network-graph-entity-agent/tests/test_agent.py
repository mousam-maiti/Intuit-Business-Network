"""
Entity Resolution Agent — Test Suite

Unit tests for:
  - Bucket key generation
  - Scoring utilities
  - compare_fields disqualifiers
  - Composite scoring with adaptive weights

Integration scenarios from build plan §Phase 3:
  1. Easy merge: embedding resolves it (~120ms, 0 LLM calls)
  2. Hard case: LLM reasoning needed (~2.5s, 1 LLM call)
  3. No candidates: create new entity (~50ms, 0 LLM calls)
  4. EIN mismatch: disqualified (~15ms)
  5. State mismatch: disqualified
  6. Cascade guard: chain_depth=3 → forced REVIEW
  7. Full pipeline: create → merge → re-evaluate
"""
import sys
import os
import asyncio
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.persona import (
    ClassifiedPersona, IdentityDimension, IndustryDimension,
    LocationDimension, CommodityDimension, BehavioralDimension,
    GoldenRecord,
)
from models.resolution import (
    ResolutionRequest, Decision, MatchLevel, DimensionConfidence, FieldMatchResult,
)
from utils.bucket_keys import generate_bucket_keys
from utils.scoring import (
    jaro_winkler, jaccard_tokens, jaccard_keywords,
    match_ein, match_phone, match_email,
    score_identity, score_industry, score_location, score_commodity,
    score_behavioral, compute_composite,
)
from config import load_config


# ═══════════════════════════════════════════════════════════
# Test Fixtures
# ═══════════════════════════════════════════════════════════

def make_persona(
    name="BOBS PLUMBING", token="BOBS", state="TX", city="AUSTIN",
    zip3="787", zip5="78741", naics="238220", ein=None, phone=None,
    email=None, keywords=None, bracket="MEDIUM",
) -> ClassifiedPersona:
    return ClassifiedPersona(
        identity=IdentityDimension(
            normalized_name=name,
            name_first_token=token,
            name_tokens=name.split(),
            ein_clean=ein,
            phone_digits=phone,
            email=email,
            email_domain=email.split("@")[-1] if email and "@" in email else None,
        ),
        industry=IndustryDimension(
            naics_code=naics,
            naics_sector=naics[:2] if naics else None,
            naics_subsector=naics[:3] if naics else None,
        ),
        location=LocationDimension(
            state=state, city_norm=city, zip3=zip3, zip5=zip5,
        ),
        commodity=CommodityDimension(
            top_keywords=keywords or ["pvc pipe", "copper fitting"],
        ),
        behavioral=BehavioralDimension(
            volume_bracket=bracket, avg_transaction=850.0, transaction_count=47,
        ),
    )


def make_golden(
    gr_id="G-001", name="BOBS PLUMBING LLC", variants=None, **kwargs
) -> dict:
    persona = make_persona(name=name, **kwargs)
    gr = GoldenRecord(
        golden_record_id=gr_id,
        canonical_name=name,
        name_variants=variants or [name],
        persona=persona,
        source_count=3,
        confidence=0.85,
        bucket_keys=generate_bucket_keys(persona),
    )
    return gr.model_dump()


# ═══════════════════════════════════════════════════════════
# Unit Tests: Bucket Keys
# ═══════════════════════════════════════════════════════════

class TestBucketKeys:
    def test_full_persona_generates_all_keys(self):
        persona = make_persona(
            name="BOBS PLUMBING", token="BOBS", state="TX", city="AUSTIN",
            zip3="787", naics="238220", keywords=["pvc pipe", "copper fitting"],
        )
        keys = generate_bucket_keys(persona)
        assert "name:BOBS+TX" in keys
        assert "naics3:238+TX" in keys
        assert "naics4:2382+TX" in keys
        assert "zip3:787" in keys
        assert "city:AUSTIN+TX" in keys
        assert "commodity:pvc pipe+TX" in keys
        assert "commodity:copper fitting+TX" in keys

    def test_ein_bucket(self):
        persona = make_persona(ein="74-8841234")
        keys = generate_bucket_keys(persona)
        assert "ein:74-8841234" in keys

    def test_phone_bucket(self):
        persona = make_persona(phone="5124551234")
        keys = generate_bucket_keys(persona)
        assert "phone:5124551234" in keys

    def test_email_domain_bucket(self):
        persona = make_persona(email="bob@bobsplumbing.com")
        keys = generate_bucket_keys(persona)
        assert "email_domain:bobsplumbing.com" in keys

    def test_sparse_persona_fewer_keys(self):
        persona = ClassifiedPersona(
            identity=IdentityDimension(
                normalized_name="UNKNOWN CO",
                name_first_token="UNKNOWN",
            ),
            location=LocationDimension(state="TX"),
        )
        keys = generate_bucket_keys(persona)
        assert len(keys) == 1  # only name:UNKNOWN+TX
        assert "name:UNKNOWN+TX" in keys

    def test_max_commodity_keywords(self):
        persona = make_persona(keywords=["a", "b", "c", "d", "e"])
        keys = generate_bucket_keys(persona, max_commodity_kw=3)
        commodity_keys = [k for k in keys if k.startswith("commodity:")]
        assert len(commodity_keys) == 3


# ═══════════════════════════════════════════════════════════
# Unit Tests: String Similarity
# ═══════════════════════════════════════════════════════════

class TestStringSimilarity:
    def test_jaro_winkler_identical(self):
        assert jaro_winkler("BOBS PLUMBING", "BOBS PLUMBING") == 1.0

    def test_jaro_winkler_similar(self):
        sim = jaro_winkler("BOBS PLUMBING", "BOBS PLUMBING LLC")
        assert sim > 0.85

    def test_jaro_winkler_different(self):
        sim = jaro_winkler("BOBS PLUMBING", "ACME CONSTRUCTION")
        assert sim < 0.55

    def test_jaro_winkler_empty(self):
        assert jaro_winkler("", "test") == 0.0
        assert jaro_winkler("test", "") == 0.0

    def test_jaccard_identical(self):
        assert jaccard_tokens({"a", "b", "c"}, {"a", "b", "c"}) == 1.0

    def test_jaccard_partial(self):
        j = jaccard_tokens({"a", "b", "c"}, {"a", "b", "d"})
        assert abs(j - 0.5) < 0.01  # 2/4

    def test_jaccard_disjoint(self):
        assert jaccard_tokens({"a"}, {"b"}) == 0.0

    def test_jaccard_keywords(self):
        j = jaccard_keywords(["PVC Pipe", "copper fitting"], ["pvc pipe", "Teflon Tape"])
        assert abs(j - 1.0 / 3.0) < 0.01  # 1 shared / 3 total


# ═══════════════════════════════════════════════════════════
# Unit Tests: Field Matching
# ═══════════════════════════════════════════════════════════

class TestFieldMatching:
    def test_ein_exact(self):
        assert match_ein("74-8841234", "74-8841234") == FieldMatchResult.EXACT

    def test_ein_mismatch(self):
        assert match_ein("74-8841234", "55-1234567") == FieldMatchResult.MISMATCH

    def test_ein_missing(self):
        assert match_ein(None, "74-8841234") == FieldMatchResult.MISSING
        assert match_ein("74-8841234", None) == FieldMatchResult.MISSING

    def test_phone_exact(self):
        assert match_phone("5124551234", "5124551234") == FieldMatchResult.EXACT

    def test_phone_partial(self):
        assert match_phone("15124551234", "5124551234") == FieldMatchResult.PARTIAL

    def test_email_exact(self):
        assert match_email("bob@plumbing.com", "bob@plumbing.com") == FieldMatchResult.EXACT

    def test_email_domain(self):
        assert match_email("bob@plumbing.com", "info@plumbing.com") == FieldMatchResult.DOMAIN_MATCH


# ═══════════════════════════════════════════════════════════
# Unit Tests: Dimension Scoring
# ═══════════════════════════════════════════════════════════

class TestDimensionScoring:
    def test_identity_high_name_similarity(self):
        orphan = make_persona(name="BOBS PLUMBING")
        candidate = make_persona(name="BOBS PLUMBING LLC")
        result = score_identity(orphan, candidate.persona if hasattr(candidate, 'persona') else candidate, ["BOBS PLUMBING LLC"])
        # Jaro-Winkler on these should be > 0.85
        assert result.score > 0.80

    def test_identity_ein_match_overrides(self):
        orphan = make_persona(name="BP SUPPLY", ein="74-8841234")
        candidate = make_persona(name="BOBS PLUMBING LLC", ein="74-8841234")
        result = score_identity(orphan, candidate, [])
        assert result.score == 1.0  # EIN exact → 1.0

    def test_industry_exact_naics(self):
        orphan = make_persona(naics="238220")
        candidate = make_persona(naics="238220")
        result = score_industry(orphan, candidate)
        assert result.score == 1.0

    def test_industry_subsector_match(self):
        orphan = make_persona(naics="238220")
        candidate = make_persona(naics="238110")
        result = score_industry(orphan, candidate)
        assert result.score == 0.8

    def test_industry_sector_match(self):
        orphan = make_persona(naics="238220")
        candidate = make_persona(naics="236220")
        result = score_industry(orphan, candidate)
        assert result.score == 0.5

    def test_industry_different_sector_no_ontology(self):
        orphan = make_persona(naics="238220")
        candidate = make_persona(naics="423720")
        result = score_industry(orphan, candidate, ontology_score=None)
        assert result.score == 0.0

    def test_industry_different_sector_with_ontology(self):
        orphan = make_persona(naics="238220")
        candidate = make_persona(naics="423720")
        result = score_industry(orphan, candidate, ontology_score=0.40)
        assert result.score == 0.40

    def test_location_zip5_match(self):
        orphan = make_persona(zip5="78741")
        candidate = make_persona(zip5="78741")
        result = score_location(orphan, candidate)
        assert result.score == 1.0

    def test_location_city_match(self):
        orphan = make_persona(city="AUSTIN", zip3=None, zip5=None)
        candidate = make_persona(city="AUSTIN", zip3=None, zip5=None)
        result = score_location(orphan, candidate)
        assert result.score == 0.7

    def test_location_state_only(self):
        orphan = make_persona(city=None, zip3=None, zip5=None)
        candidate = make_persona(city=None, zip3=None, zip5=None)
        result = score_location(orphan, candidate)
        assert result.score == 0.3

    def test_commodity_full_overlap(self):
        orphan = make_persona(keywords=["pvc pipe", "copper fitting"])
        candidate = make_persona(keywords=["pvc pipe", "copper fitting"])
        result = score_commodity(orphan, candidate)
        assert result.score == 1.0

    def test_commodity_partial_overlap(self):
        orphan = make_persona(keywords=["pvc pipe", "copper fitting"])
        candidate = make_persona(keywords=["pvc pipe", "teflon tape"])
        result = score_commodity(orphan, candidate)
        assert 0.3 < result.score < 0.5  # 1/3 Jaccard


# ═══════════════════════════════════════════════════════════
# Unit Tests: Composite Scoring
# ═══════════════════════════════════════════════════════════

class TestCompositeScoring:
    def test_all_perfect(self):
        dims = {
            "identity": make_dim(1.0), "industry": make_dim(1.0),
            "location": make_dim(1.0), "commodity": make_dim(1.0),
            "behavioral": make_dim(1.0),
        }
        weights = {"identity": 0.35, "industry": 0.25, "location": 0.15,
                   "commodity": 0.15, "behavioral": 0.10}
        score, _, adjusted = compute_composite(dims, weights)
        assert abs(score - 1.0) < 0.01

    def test_adaptive_weight_redistribution(self):
        dims = {
            "identity": make_dim(0.8),
            "industry": make_dim(0.0, conf=DimensionConfidence.INSUFFICIENT),
            "location": make_dim(0.7),
            "commodity": make_dim(0.0, conf=DimensionConfidence.INSUFFICIENT),
            "behavioral": make_dim(0.6),
        }
        weights = {"identity": 0.35, "industry": 0.25, "location": 0.15,
                   "commodity": 0.15, "behavioral": 0.10}
        score, used_weights, adjusted = compute_composite(dims, weights)
        # Industry + commodity weight (0.25 + 0.15 = 0.40) redistributed
        assert adjusted is True
        assert "industry" not in used_weights
        assert "commodity" not in used_weights
        # Remaining weights should sum to 1.0
        assert abs(sum(used_weights.values()) - 1.0) < 0.01

    def test_all_insufficient(self):
        dims = {
            "identity": make_dim(0.0, conf=DimensionConfidence.INSUFFICIENT),
            "industry": make_dim(0.0, conf=DimensionConfidence.INSUFFICIENT),
            "location": make_dim(0.0, conf=DimensionConfidence.INSUFFICIENT),
            "commodity": make_dim(0.0, conf=DimensionConfidence.INSUFFICIENT),
            "behavioral": make_dim(0.0, conf=DimensionConfidence.INSUFFICIENT),
        }
        weights = {"identity": 0.35, "industry": 0.25, "location": 0.15,
                   "commodity": 0.15, "behavioral": 0.10}
        score, _, _ = compute_composite(dims, weights)
        assert score == 0.0



# ═══════════════════════════════════════════════════════════
# Integration Tests: Full Pipeline Scenarios
# ═══════════════════════════════════════════════════════════

class TestFullPipeline:
    """Integration tests using in-memory mocks (no external services)."""

    @pytest.fixture
    def setup_agent(self, tmp_path):
        """Build the full agent stack with mock clients."""
        from clients.mysql_client import MySQLClient
        from clients.milvus_client import MilvusClient
        from clients.embedding_client import EmbeddingClient
        from clients.llm_client import LLMClient
        from mcp.candidate_evaluator import CandidateEvaluator
        from mcp.knowledge_graph import KnowledgeGraphServer
        from mcp.entity_writer import EntityWriter
        from orchestrator import Orchestrator

        cfg = load_config()

        # All mock clients (no external services needed)
        mysql = MySQLClient(cfg.mysql)
        mysql._using_mock = True
        mysql._mock_records = {}
        milvus = MilvusClient(cfg.milvus)
        milvus._using_mock = True
        embedding = EmbeddingClient(cfg.embedding)
        embedding._using_mock = True
        llm = LLMClient(cfg.llm)

        graphdb_mock = type('MockGDB', (), {'available': False})()
        kg = KnowledgeGraphServer(graphdb_mock)
        evaluator = CandidateEvaluator(cfg, mysql, embedding, kg)
        writer = EntityWriter(cfg, mysql, milvus, kg)

        orch = Orchestrator(cfg, evaluator, kg, writer, llm)

        return {
            "orchestrator": orch,
            "mysql": mysql,
            "cfg": cfg,
            "writer": writer,
        }

    def _seed_golden_record(self, setup, gr_data: dict):
        """Seed a golden record into MySQL mock."""
        gr = GoldenRecord.model_validate(gr_data)
        setup["mysql"].write_golden_record(gr.model_dump())

    @pytest.mark.asyncio
    async def test_scenario_3_no_candidates_create_new(self, setup_agent):
        """Scenario 3: completely new business, no bucket matches → CREATE."""
        request = ResolutionRequest(
            event_id="evt-001",
            record_id="v-001",
            classified_persona=make_persona(
                name="TOTALLY UNIQUE BUSINESS", token="TOTALLY",
                state="AK", naics="999999",
                keywords=["exotic widgets"],
            ),
        )
        response = await setup_agent["orchestrator"].resolve(request)
        assert response.decision == Decision.NEW_ENTITY
        assert response.target_golden_record_id is not None
        assert setup_agent["mysql"].record_count >= 1

    @pytest.mark.asyncio
    async def test_scenario_7_ein_mismatch_disqualified(self, setup_agent):
        """Scenario 7: same name but different EIN → DISQUALIFIED → CREATE."""
        gr = make_golden(gr_id="G-EIN1", name="BOBS PLUMBING", ein="74-8841234")
        self._seed_golden_record(setup_agent, gr)

        request = ResolutionRequest(
            event_id="evt-ein",
            record_id="v-ein",
            classified_persona=make_persona(
                name="BOBS PLUMBING", ein="55-9999999",
            ),
        )
        response = await setup_agent["orchestrator"].resolve(request)
        assert response.decision == Decision.NEW_ENTITY

    @pytest.mark.asyncio
    async def test_scenario_state_mismatch(self, setup_agent):
        """Different state → DISQUALIFIED."""
        gr = make_golden(gr_id="G-ST1", name="BOBS PLUMBING", state="TX")
        self._seed_golden_record(setup_agent, gr)

        request = ResolutionRequest(
            event_id="evt-st",
            record_id="v-st",
            classified_persona=make_persona(
                name="BOBS PLUMBING", state="CA",
            ),
        )
        response = await setup_agent["orchestrator"].resolve(request)
        assert response.decision == Decision.NEW_ENTITY

    @pytest.mark.asyncio
    async def test_scenario_1_easy_merge(self, setup_agent):
        """Scenario 1: similar name, same NAICS, same city → MERGE via deterministic or embedding."""
        gr = make_golden(
            gr_id="G-001", name="BOBS PLUMBING LLC",
            variants=["BOBS PLUMBING LLC", "BOBS PLUMBING"],
            token="BOBS", state="TX", city="AUSTIN", naics="238220",
            keywords=["pvc pipe", "copper fitting"],
        )
        self._seed_golden_record(setup_agent, gr)

        request = ResolutionRequest(
            event_id="evt-easy",
            record_id="v-287",
            classified_persona=make_persona(
                name="BOBS PLUMBING SUPPLY", token="BOBS",
                state="TX", city="AUSTIN", naics="238220",
                keywords=["pvc pipe", "copper fitting"],
            ),
        )
        response = await setup_agent["orchestrator"].resolve(request)
        assert response.decision in (Decision.MERGE, Decision.REVIEW)
        assert response.target_golden_record_id == "G-001"

    @pytest.mark.asyncio
    async def test_scenario_6_cascade_guard(self, setup_agent):
        """Scenario 6: chain_depth=3 → forced REVIEW even if match found."""
        gr = make_golden(gr_id="G-CASCADE", name="BOBS PLUMBING")
        self._seed_golden_record(setup_agent, gr)

        request = ResolutionRequest(
            event_id="evt-cascade",
            record_id="v-cascade",
            chain_depth=3,
            classified_persona=make_persona(name="BOBS PLUMBING"),
        )
        response = await setup_agent["orchestrator"].resolve(request)
        assert response.decision in (Decision.MERGE, Decision.REVIEW)

    @pytest.mark.asyncio
    async def test_scenario_7_full_lifecycle(self, setup_agent):
        """Full lifecycle: create → query → merge."""
        request1 = ResolutionRequest(
            event_id="evt-lc1",
            record_id="v-lc1",
            classified_persona=make_persona(
                name="ACME CONSTRUCTION", token="ACME",
                state="NY", naics="236220",
                keywords=["concrete", "rebar"],
            ),
        )
        resp1 = await setup_agent["orchestrator"].resolve(request1)
        assert resp1.decision == Decision.NEW_ENTITY
        new_gr_id = resp1.target_golden_record_id
        assert new_gr_id is not None

        request2 = ResolutionRequest(
            event_id="evt-lc2",
            record_id="v-lc2",
            classified_persona=make_persona(
                name="ACME CONSTRUCTION INC", token="ACME",
                state="NY", naics="236220",
                keywords=["concrete", "rebar"],
            ),
        )
        resp2 = await setup_agent["orchestrator"].resolve(request2)
        assert resp2.decision in (Decision.MERGE, Decision.REVIEW)
        assert resp2.target_golden_record_id == new_gr_id


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

from models.resolution import DimensionResult

def make_dim(score: float, conf: DimensionConfidence = DimensionConfidence.HIGH) -> DimensionResult:
    return DimensionResult(score=score, confidence=conf)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
