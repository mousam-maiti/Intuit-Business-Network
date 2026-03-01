"""
FastMCP instance + AppContext + lifespan.

Circular import prevention:
  app.py          → creates FastMCP instance + AppContext (no tool imports)
  tools/*.py      → imports `mcp` from app.py, decorates functions with @mcp.tool()
  server.py       → imports `mcp` from app.py, then imports tools/* to register, calls mcp.run()
"""
from __future__ import annotations
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP, Context

from config import AgentConfig, load_config
from clients.mysql_client import MySQLClient
from clients.milvus_client import MilvusClient
from clients.embedding_client import EmbeddingClient
from clients.llm_client import LLMClient
from clients.neo4j_client import Neo4jClient
from clients.redis_client import RedisClient
from models.persona import GoldenRecord, ClassifiedPersona
from utils.bucket_keys import generate_bucket_keys

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Shared resources available to all MCP tools via lifespan context."""
    config: AgentConfig
    mysql: MySQLClient
    milvus: MilvusClient
    embedding: EmbeddingClient
    llm: LLMClient
    neo4j: Neo4jClient
    redis: RedisClient


def _bootstrap_company_golden_records(ctx: "AppContext"):
    """Ensure all QB companies have QB_USER golden records before pipeline runs.

    Reads company source data from MySQL, writes golden records to Neo4j (primary).
    This eliminates the race condition where IC vendor records arrive before
    any customer record triggers QB_USER creation via _ensure_company_golden_record.
    """
    companies = ctx.mysql.get_all_companies()

    created = 0
    for company in companies:
        cid = str(company.get("company_id", ""))
        if not cid:
            continue
        existing = ctx.neo4j.get_golden_record(cid)
        if existing:
            continue

        name = company.get("company_name", f"Company {cid}")
        ein_raw = company.get("ein") or ""
        ein_clean = ein_raw.replace("-", "").strip() or None

        persona = ClassifiedPersona()
        persona.identity.normalized_name = name
        persona.identity.name_first_token = name.split()[0].upper() if name else ""
        persona.identity.name_tokens = [t.upper() for t in name.split()] if name else []
        persona.identity.ein_clean = ein_clean
        persona.identity.phone_digits = (company.get("phone") or "").replace("-", "").replace(" ", "")[-10:] or None
        persona.identity.email = company.get("email")
        persona.identity.email_domain = (company.get("email") or "").split("@")[-1] if company.get("email") else None

        persona.location.state = company.get("state") or ""
        persona.location.city_norm = (company.get("city") or "").upper() or None
        zip_val = company.get("zip") or ""
        persona.location.zip5 = zip_val[:5] if len(zip_val) >= 5 else None
        persona.location.zip3 = zip_val[:3] if len(zip_val) >= 3 else None

        persona.industry.original_category = company.get("industry_category")

        bucket_keys = generate_bucket_keys(persona, ctx.config.buckets.max_commodity_keywords)

        gr = GoldenRecord(
            golden_record_id=cid,
            canonical_name=name,
            name_variants=[name],
            persona=persona,
            source_count=1,
            confidence=1.0,
            status="ACTIVE",
            entity_type="QB_USER",
            source_records=[],
            bucket_keys=bucket_keys,
        )
        ctx.neo4j.upsert_entity(gr.model_dump())
        created += 1

    if created:
        logger.info(f"Bootstrapped {created} QB_USER golden records to Neo4j")
    else:
        logger.info("All QB_USER golden records already exist — no bootstrap needed")


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Initialize all clients on startup, tear down on shutdown."""
    config = load_config()
    logger.info(f"Loading config: server={config.server.name} port={config.server.port}")

    mysql = MySQLClient(config.mysql)
    neo4j = Neo4jClient(config.neo4j)
    redis = RedisClient(config.redis)
    milvus = MilvusClient(config.milvus)
    embedding = EmbeddingClient(config.embedding)
    llm = LLMClient(config.llm)

    await mysql.connect()
    await neo4j.connect()
    await redis.connect()
    await milvus.connect()
    await embedding.connect()
    await llm.connect()

    logger.info(
        f"Clients initialized: "
        f"mysql={'mock' if mysql.using_mock else 'live'} "
        f"neo4j={'available' if neo4j.available else 'unavailable'} "
        f"redis={'available' if redis.available else 'unavailable'} "
        f"milvus={'mock' if milvus.using_mock else 'live'} "
        f"embedding={'mock' if embedding.is_mock else 'live'} "
        f"llm={'available' if llm.available else 'unavailable'}"
    )

    ctx = AppContext(
        config=config,
        mysql=mysql,
        milvus=milvus,
        embedding=embedding,
        llm=llm,
        neo4j=neo4j,
        redis=redis,
    )

    _bootstrap_company_golden_records(ctx)

    try:
        yield ctx
    finally:
        await mysql.close()
        await neo4j.close()
        await redis.close()
        await milvus.close()
        logger.info("MCP Server shut down — all clients released")


# ── FastMCP instance ─────────────────────────────────────────

# Load config early so host/port are available for FastMCP constructor
_boot_config = load_config()

mcp = FastMCP(
    "qb-network-graph-mcp",
    lifespan=app_lifespan,
    host=_boot_config.server.host,
    port=_boot_config.server.port,
)
