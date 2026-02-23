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
from clients.graphdb_client import GraphDBClient
from clients.embedding_client import EmbeddingClient
from clients.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Shared resources available to all MCP tools via lifespan context."""
    config: AgentConfig
    mysql: MySQLClient
    milvus: MilvusClient
    graphdb: GraphDBClient
    embedding: EmbeddingClient
    llm: LLMClient


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Initialize all clients on startup, tear down on shutdown."""
    config = load_config()
    logger.info(f"Loading config: server={config.server.name} port={config.server.port}")

    mysql = MySQLClient(config.mysql)
    milvus = MilvusClient(config.milvus)
    graphdb = GraphDBClient(config.knowledge_graph)
    embedding = EmbeddingClient(config.embedding)
    llm = LLMClient(config.llm)

    await mysql.connect()
    await milvus.connect()
    await graphdb.connect()
    await embedding.connect()
    await llm.connect()

    logger.info(
        f"Clients initialized: "
        f"mysql={'mock' if mysql.using_mock else 'live'} "
        f"milvus={'mock' if milvus.using_mock else 'live'} "
        f"graphdb={'available' if graphdb.available else 'unavailable'} "
        f"embedding={'mock' if embedding.is_mock else 'live'} "
        f"llm={'available' if llm.available else 'unavailable'}"
    )

    ctx = AppContext(
        config=config,
        mysql=mysql,
        milvus=milvus,
        graphdb=graphdb,
        embedding=embedding,
        llm=llm,
    )

    try:
        yield ctx
    finally:
        await mysql.close()
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
