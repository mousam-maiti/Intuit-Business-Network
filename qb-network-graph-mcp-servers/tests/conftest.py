"""
Test fixtures for MCP server tests.

Provides mock AppContext with in-memory clients and services for all tools.
"""
import pytest
import pytest_asyncio
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import AgentConfig, MySQLConfig, EmbeddingConfig, LLMConfig, Neo4jConfig, RedisConfig
from clients.mysql_client import MySQLClient
from clients.embedding_client import EmbeddingClient
from clients.llm_client import LLMClient
from clients.neo4j_client import Neo4jClient
from clients.redis_client import RedisClient
from app import AppContext

from services.candidate_service import CandidateService
from services.entity_writer_service import EntityWriterService
from services.search_service import SearchService
from services.knowledge_graph_service import KnowledgeGraphService
from services.sync_service import SyncService

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
def neo4j_client(config):
    """Neo4j client in mock mode (in-memory dict)."""
    client = Neo4jClient(config.neo4j)
    client._using_mock = True
    return client


@pytest.fixture
def redis_client(config):
    """Redis client — unavailable (no real Redis in tests)."""
    client = RedisClient(config.redis)
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
def app_context(config, mysql_client, neo4j_client, redis_client, embedding_client, llm_client):
    """Full AppContext with mock clients and services."""
    candidate_service = CandidateService(
        entity_repo=neo4j_client, embedding=embedding_client, config=config,
    )
    entity_writer_service = EntityWriterService(
        entity_repo=neo4j_client, relationship_repo=neo4j_client,
        audit_repo=neo4j_client, cache=redis_client, config=config,
    )
    search_service = SearchService(
        entity_repo=neo4j_client, relationship_repo=neo4j_client,
        audit_repo=neo4j_client, search_repo=neo4j_client,
        embedding=embedding_client, cache=redis_client,
    )
    knowledge_graph_service = KnowledgeGraphService(
        entity_repo=neo4j_client, relationship_repo=neo4j_client, cache=redis_client,
    )
    sync_service = SyncService(
        entity_repo=neo4j_client, relationship_repo=neo4j_client,
        audit_repo=neo4j_client, cache=redis_client, embedding=embedding_client,
    )

    return AppContext(
        config=config,
        candidate_service=candidate_service,
        entity_writer_service=entity_writer_service,
        search_service=search_service,
        knowledge_graph_service=knowledge_graph_service,
        sync_service=sync_service,
        mysql=mysql_client,
        embedding=embedding_client,
        llm=llm_client,
        neo4j=neo4j_client,
        redis=redis_client,
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
    """A sample golden record seeded in Neo4j mock."""
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
def seeded_neo4j(neo4j_client, sample_golden_record):
    """Neo4j client with a sample golden record pre-seeded."""
    neo4j_client.upsert_entity(sample_golden_record.model_dump())
    return neo4j_client
