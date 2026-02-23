"""
Test fixtures for MCP server tests.

Provides mock AppContext with in-memory clients for all tools.
"""
import pytest
import pytest_asyncio
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import AgentConfig, MySQLConfig, MilvusConfig, EmbeddingConfig, LLMConfig, KnowledgeGraphConfig
from clients.mysql_client import MySQLClient
from clients.milvus_client import MilvusClient
from clients.graphdb_client import GraphDBClient
from clients.embedding_client import EmbeddingClient
from clients.llm_client import LLMClient
from app import AppContext
from models.persona import (
    ClassifiedPersona, IdentityDimension, IndustryDimension,
    LocationDimension, CommodityDimension, BehavioralDimension,
    GoldenRecord,
)
from utils.bucket_keys import generate_bucket_keys


@pytest.fixture
def config():
    """Default test config — all services use mock/in-memory."""
    return AgentConfig()


@pytest.fixture
def mysql_client(config):
    """MySQL client in mock mode (in-memory dict)."""
    client = MySQLClient(config.mysql)
    client._using_mock = True
    return client


@pytest.fixture
def milvus_client(config):
    """Milvus client in mock mode."""
    client = MilvusClient(config.milvus)
    client._using_mock = True
    client._embed_provider = "none"
    return client


@pytest.fixture
def graphdb_client(config):
    """GraphDB client — unavailable (no real GraphDB in tests)."""
    client = GraphDBClient(config.knowledge_graph)
    return client


@pytest.fixture
def embedding_client(config):
    """Embedding client in mock mode."""
    client = EmbeddingClient(config.embedding)
    client._using_mock = True
    return client


@pytest.fixture
def llm_client(config):
    """LLM client — unavailable."""
    return LLMClient(config.llm)


@pytest.fixture
def app_context(config, mysql_client, milvus_client, graphdb_client, embedding_client, llm_client):
    """Full AppContext with mock clients."""
    return AppContext(
        config=config,
        mysql=mysql_client,
        milvus=milvus_client,
        graphdb=graphdb_client,
        embedding=embedding_client,
        llm=llm_client,
    )


@pytest.fixture
def sample_persona():
    """A sample classified persona for testing."""
    return ClassifiedPersona(
        identity=IdentityDimension(
            normalized_name="Bob's Plumbing LLC",
            name_first_token="BOBS",
            name_tokens=["BOBS", "PLUMBING", "LLC"],
            ein_clean="743218976",
            phone_digits="5124551234",
            email="bob@bobsplumbing.com",
            email_domain="bobsplumbing.com",
        ),
        industry=IndustryDimension(
            naics_code="238220",
            naics_sector="23",
            naics_subsector="238",
            commodity_keywords=["pvc pipe", "copper fittings"],
        ),
        location=LocationDimension(
            state="TX",
            city_norm="AUSTIN",
            zip3="787",
            zip5="78704",
        ),
        commodity=CommodityDimension(
            top_keywords=["pvc pipe", "copper fittings", "plumbing supplies"],
        ),
        behavioral=BehavioralDimension(
            volume_bracket="MEDIUM",
            avg_transaction=250.0,
            transaction_count=45,
        ),
    )


@pytest.fixture
def sample_golden_record(sample_persona):
    """A sample golden record seeded in MySQL mock."""
    return GoldenRecord(
        golden_record_id="G-test0001",
        canonical_name="Bob's Plumbing LLC",
        name_variants=["Bob's Plumbing LLC", "Bobs Plumbing"],
        persona=sample_persona,
        source_count=3,
        confidence=0.85,
        status="ACTIVE",
        entity_type="QB_USER",
        source_records=["R-001", "R-002", "R-003"],
        bucket_keys=generate_bucket_keys(sample_persona),
    )


@pytest.fixture
def seeded_mysql(mysql_client, sample_golden_record):
    """MySQL client with a sample golden record pre-seeded."""
    mysql_client.write_golden_record(sample_golden_record)
    return mysql_client
