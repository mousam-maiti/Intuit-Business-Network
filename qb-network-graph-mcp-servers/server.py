"""
MCP Server entry point.

Imports all tool modules to register @mcp.tool() decorators,
then runs the FastMCP server with Streamable HTTP transport.
Also mounts sync HTTP endpoints for Paimon → Neo4j data push.

Usage:
    python server.py                        # Run server on configured port
    mcp dev server.py                       # MCP Inspector (development)
"""
import logging
import os
import sys
import threading
from pathlib import Path

# Add shared llm_providers package to path
_llm_pkg = str(Path(__file__).resolve().parent.parent / "qb-network-graph-llm-providers")
if _llm_pkg not in sys.path:
    sys.path.insert(0, _llm_pkg)

# Configure logging before any imports that use it
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Import the FastMCP instance (no tools registered yet)
from app import mcp

# Import all tool modules — this triggers @mcp.tool() registration
import tools.candidate_tools       # noqa: F401 — find_candidates, compare_fields, semantic_similarity
import tools.knowledge_graph_tools # noqa: F401 — query_ontology, check_shared_context, batch_industry_filter
import tools.entity_writer_tools   # noqa: F401 — merge_into_golden_record, create_golden_record, submit_for_review, merge_golden_records, log_decision
import tools.search_tools          # noqa: F401 — search_entities, describe_entity, query_network, aggregate_stats, search_by_relationship, get_company_connections, get_merge_history, traverse_supply_chain

from config import load_config
from utils import telemetry

logger.info("All 19 tools registered")


def _start_sync_api(config):
    """Run the sync HTTP API on port MCP_PORT + 1 in a background thread."""
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from routes.sync import router as sync_router
    from services.sync_service import SyncService
    from services.candidate_service import CandidateService
    from clients.neo4j_client import Neo4jClient
    from clients.redis_client import RedisClient
    import asyncio

    sync_app = FastAPI(title="MCP Sync API")

    # Instrument sync app with OTEL
    if config.telemetry.enabled:
        telemetry.instrument_app(sync_app)
    sync_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )
    sync_app.include_router(sync_router)

    @sync_app.on_event("startup")
    async def startup():
        from clients.embedding_client import EmbeddingClient
        neo4j = Neo4jClient(config.neo4j)
        redis = RedisClient(config.redis)
        embedding = EmbeddingClient(config.embedding)
        await neo4j.connect()
        await redis.connect()
        await embedding.connect()
        sync_service = SyncService(
            entity_repo=neo4j, relationship_repo=neo4j,
            audit_repo=neo4j, cache=redis, embedding=embedding,
        )
        candidate_service = CandidateService(
            entity_repo=neo4j, embedding=embedding, config=config,
        )
        sync_app.state.sync_service = sync_service
        sync_app.state.candidate_service = candidate_service
        sync_app.state.neo4j = neo4j
        sync_app.state.redis = redis
        logger.info(f"Sync API started on port {config.server.port + 1}")

    @sync_app.on_event("shutdown")
    async def shutdown():
        if hasattr(sync_app.state, "neo4j"):
            await sync_app.state.neo4j.close()
        if hasattr(sync_app.state, "redis"):
            await sync_app.state.redis.close()

    sync_port = config.server.port + 1
    uvicorn.run(sync_app, host=config.server.host, port=sync_port, log_level="info")


def main():
    config = load_config()

    # Initialize OTEL telemetry
    otel_active = False
    if config.telemetry.enabled:
        otel_active = telemetry.setup(
            service_name=config.telemetry.service_name,
            otlp_endpoint=config.telemetry.otlp_endpoint,
            export_interval_ms=config.telemetry.export_interval_ms,
        )

    # Start sync API in background thread
    sync_thread = threading.Thread(target=_start_sync_api, args=(config,), daemon=True)
    sync_thread.start()

    logger.info(f"Starting MCP Server: {config.server.name}")
    logger.info(f"Transport: Streamable HTTP on {config.server.host}:{config.server.port}")
    logger.info(f"Sync API: HTTP on {config.server.host}:{config.server.port + 1}")
    logger.info(f"OTEL: {'ACTIVE' if otel_active else 'disabled'}")
    logger.info("MCP Server READY")

    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
