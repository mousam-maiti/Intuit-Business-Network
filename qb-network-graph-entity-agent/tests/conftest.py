"""
Shared fixtures and markers for the entity resolution agent test suite.

All fixtures use mock/offline mode — no external services required.
"""
from __future__ import annotations
import pytest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Shared llm_providers package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "qb-network-graph-llm-providers"))

from models.persona import (
    ClassifiedPersona, IdentityDimension, IndustryDimension,
    LocationDimension, CommodityDimension, BehavioralDimension,
    SparsityScores, GoldenRecord,
)
from config import (
    AgentConfig, MySQLConfig, EmbeddingConfig,
    KnowledgeGraphConfig, LLMConfig, load_config,
)


# ── Markers ────────────────────────────────────────────────────

def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: post-deployment live service tests")
    config.addinivalue_line("markers", "slow: tests that take >1s")
    config.addinivalue_line("markers", "unit: pure unit tests")
    config.addinivalue_line("markers", "integration: integration tests")


# ── Persona & Golden Record Factories ──────────────────────────

@pytest.fixture
def persona_factory():
    """Returns a make_persona(**kwargs) factory with sensible defaults."""
    def make_persona(
        name="BOBS PLUMBING",
        name_first_token="BOBS",
        name_tokens=None,
        legal_suffix="LLC",
        ein=None,
        phone=None,
        email=None,
        email_domain=None,
        state="TX",
        city="AUSTIN",
        zip5="78701",
        zip3="787",
        naics_code="238220",
        naics_sector="23",
        naics_subsector="238",
        original_category="Plumbing",
        commodity_keywords=None,
        top_keywords=None,
        service_categories=None,
        volume_bracket=None,
        avg_transaction=None,
        transaction_count=None,
    ):
        if name_tokens is None:
            name_tokens = name.split() if name else []
        if commodity_keywords is None:
            commodity_keywords = ["pvc pipe", "copper fittings"]
        if top_keywords is None:
            top_keywords = ["pvc pipe", "copper fittings"]
        if service_categories is None:
            service_categories = ["plumbing"]

        return ClassifiedPersona(
            identity=IdentityDimension(
                normalized_name=name,
                name_first_token=name_first_token,
                name_tokens=name_tokens,
                legal_suffix=legal_suffix,
                ein_clean=ein,
                phone_digits=phone,
                email=email,
                email_domain=email_domain,
            ),
            industry=IndustryDimension(
                naics_code=naics_code,
                naics_sector=naics_sector,
                naics_subsector=naics_subsector,
                original_category=original_category,
                commodity_keywords=commodity_keywords,
            ),
            location=LocationDimension(
                state=state,
                city_norm=city,
                zip3=zip3,
                zip5=zip5,
            ),
            commodity=CommodityDimension(
                top_keywords=top_keywords,
                service_categories=service_categories,
            ),
            behavioral=BehavioralDimension(
                volume_bracket=volume_bracket,
                avg_transaction=avg_transaction,
                transaction_count=transaction_count,
            ),
            sparsity=SparsityScores(identity=3, industry=2, location=3, commodity=2, behavioral=0),
        )

    return make_persona


@pytest.fixture
def golden_factory(persona_factory):
    """Returns a make_golden(gr_id, name, ...) factory wrapping persona in GoldenRecord."""
    def make_golden(
        gr_id="G-test0001",
        name="BOBS PLUMBING",
        status="ACTIVE",
        entity_type="PHANTOM",
        confidence=0.5,
        source_count=1,
        source_records=None,
        bucket_keys=None,
        name_variants=None,
        **persona_kwargs,
    ):
        persona = persona_factory(name=name, **persona_kwargs)
        return GoldenRecord(
            golden_record_id=gr_id,
            canonical_name=name,
            name_variants=name_variants or [name],
            persona=persona,
            source_count=source_count,
            confidence=confidence,
            status=status,
            entity_type=entity_type,
            source_records=source_records or ["orphan-1"],
            bucket_keys=bucket_keys or [],
        )

    return make_golden


# ── Config ─────────────────────────────────────────────────────

@pytest.fixture
def default_config():
    """Load AgentConfig from agent-config.yaml."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "agent-config.yaml")
    if os.path.exists(config_path):
        return load_config(config_path)
    return AgentConfig()


# ── Mock Clients ───────────────────────────────────────────────



@pytest.fixture
def mock_embedding():
    """EmbeddingClient in mock mode."""
    from clients.embedding_client import EmbeddingClient
    client = EmbeddingClient(EmbeddingConfig())
    client._using_mock = True
    return client


@pytest.fixture
def mock_graphdb():
    """GraphDBClient with _available=False."""
    from clients.graphdb_client import GraphDBClient
    client = GraphDBClient(KnowledgeGraphConfig())
    client._available = False
    return client


@pytest.fixture
def mock_llm():
    """LLMClient with _available=False."""
    from clients.llm_client import LLMClient
    client = LLMClient(LLMConfig())
    client._available = False
    return client


# ── Mock MCP Servers ───────────────────────────────────────────

@pytest.fixture
def mock_kg(mock_graphdb):
    """KnowledgeGraphServer with unavailable GraphDB."""
    from mcp.knowledge_graph import KnowledgeGraphServer
    return KnowledgeGraphServer(mock_graphdb)


@pytest.fixture
def mock_evaluator(default_config, mock_mysql, mock_embedding, mock_kg):
    """CandidateEvaluator with all mocks."""
    from mcp.candidate_evaluator import CandidateEvaluator
    return CandidateEvaluator(
        config=default_config,
        mysql=mock_mysql,
        embedding=mock_embedding,
        knowledge_graph=mock_kg,
    )


@pytest.fixture
def mock_writer(default_config, mock_mysql, mock_milvus, mock_kg):
    """EntityWriter with all mocks."""
    from mcp.entity_writer import EntityWriter
    return EntityWriter(
        config=default_config,
        mysql=mock_mysql,
        milvus=mock_milvus,
        knowledge_graph=mock_kg,
    )


@pytest.fixture
def mock_orchestrator(default_config, mock_evaluator, mock_kg, mock_writer, mock_llm):
    """Full Orchestrator with all mocks."""
    from orchestrator import Orchestrator
    return Orchestrator(
        config=default_config,
        evaluator=mock_evaluator,
        knowledge_graph=mock_kg,
        writer=mock_writer,
        llm=mock_llm,
    )
