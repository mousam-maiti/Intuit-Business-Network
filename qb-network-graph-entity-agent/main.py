"""
Entity Resolution Agent Service — FastAPI application.

Endpoints (all under /api/v1/):
  POST /api/v1/resolve       — resolve an orphan record
  POST /api/v1/re-evaluate   — re-evaluate a golden record after enrichment
  GET  /api/v1/health        — health check
  GET  /api/v1/stats         — runtime statistics

v5: SOLID refactoring — abstract interfaces, DI, service layer, API versioning.
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import JSONResponse

from config import load_config
from exceptions import AgentError, AgentNotInitializedError

# ── Clients ──────────────────────────────────────────────────
from clients.mcp_client import MCPToolClient
from clients.llm_client import LLMClient
from clients.mcp_candidate_finder import MCPCandidateFinder
from clients.mcp_field_comparator import MCPFieldComparator
from clients.mcp_similarity_provider import MCPSimilarityProvider
from clients.gemini_llm_reasoner import GeminiLLMReasoner
from clients.mcp_entity_store import MCPEntityStore
from clients.mcp_audit_logger import MCPAuditLogger

# ── Services ─────────────────────────────────────────────────
from services.resolution_service import ResolutionService
from services.reevaluation_service import ReEvaluationService

# ── Routes ───────────────────────────────────────────────────
from routes.v1.resolution import router as resolution_router
from routes.v1.reevaluation import router as reevaluation_router
from routes.v1.health import router as health_router

from utils import telemetry

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    HAS_FASTAPI_OTEL = True
except ImportError:
    HAS_FASTAPI_OTEL = False

logging.basicConfig(
    level=os.environ.get("AGENT_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(name)-30s %(levelname)-5s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wire all components on startup via dependency injection."""
    app.state.stats = {
        "requests": 0, "merges": 0, "creates": 0,
        "reviews": 0, "errors": 0, "start_time": time.time(),
    }

    logger.info("Loading config...")
    cfg = load_config()

    # ── Initialize OTEL telemetry ───────────────────────────
    otel_active = False
    if cfg.telemetry.enabled:
        otel_active = telemetry.setup(
            service_name=cfg.telemetry.service_name,
            otlp_endpoint=cfg.telemetry.otlp_endpoint,
            export_interval_ms=cfg.telemetry.export_interval_ms,
        )

    # ── Connect to MCP Server ─────────────────────────────
    logger.info(f"Connecting to MCP Server at {cfg.mcp_server.url}...")
    mcp = MCPToolClient(url=cfg.mcp_server.url, timeout_ms=cfg.mcp_server.timeout_ms)
    await mcp.connect()
    app.state.mcp_client = mcp

    # ── LLM stays local (not an MCP tool) ─────────────────
    llm = LLMClient(cfg.llm)
    await llm.connect()

    # ── Build interface implementations ───────────────────
    finder = MCPCandidateFinder(mcp)
    comparator = MCPFieldComparator(mcp)
    similarity = MCPSimilarityProvider(mcp)
    reasoner = GeminiLLMReasoner(llm)
    store = MCPEntityStore(mcp)
    audit = MCPAuditLogger(mcp)

    app.state.llm_reasoner = reasoner

    # ── Build services ────────────────────────────────────
    app.state.resolution_service = ResolutionService(
        finder=finder,
        comparator=comparator,
        similarity=similarity,
        reasoner=reasoner,
        store=store,
        audit=audit,
        config=cfg,
    )
    app.state.reevaluation_service = ReEvaluationService(
        finder=finder,
        comparator=comparator,
        store=store,
        config=cfg,
    )

    app.state.cfg = cfg

    logger.info("=" * 60)
    logger.info("Entity Resolution Agent Service READY")
    logger.info(f"  MCP Server: {cfg.mcp_server.url} ({'connected' if mcp.connected else 'FAILED'})")
    logger.info(f"  MCP Tools:  {len(mcp._tool_names)} available")
    logger.info(f"  LLM:        {'connected' if llm.available else 'UNAVAILABLE'}")
    logger.info(f"  OTEL:       {'ACTIVE' if otel_active else 'disabled'}")
    logger.info(f"  Thresholds: merge>{cfg.thresholds.auto_merge} review>{cfg.thresholds.human_review}")
    logger.info("=" * 60)

    yield

    # ── Shutdown ──────────────────────────────────────────
    logger.info("Agent service shutting down...")
    await mcp.close()
    logger.info("Agent service stopped.")


# ── FastAPI app ─────────────────────────────────────────────

app = FastAPI(
    title="QB Entity Resolution Agent",
    description="Resolves orphan business records against golden record corpus",
    version="4.0.0",
    lifespan=lifespan,
)

if HAS_FASTAPI_OTEL:
    FastAPIInstrumentor.instrument_app(app)


# ── Exception handlers ──────────────────────────────────────

@app.exception_handler(AgentNotInitializedError)
async def agent_not_initialized_handler(request: Request, exc: AgentNotInitializedError):
    return JSONResponse(status_code=503, content={"error": exc.code, "detail": exc.message})


@app.exception_handler(AgentError)
async def agent_error_handler(request: Request, exc: AgentError):
    return JSONResponse(status_code=500, content={"error": exc.code, "detail": exc.message})


# ── Mount routes under /api/v1 ──────────────────────────────

api = APIRouter(prefix="/api/v1")
api.include_router(resolution_router)
api.include_router(reevaluation_router)
api.include_router(health_router)

app.include_router(api)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8085, reload=True)
