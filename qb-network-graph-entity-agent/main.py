"""
Entity Resolution Agent Service — FastAPI application.

Endpoints:
  POST /resolve       — resolve an orphan record
  POST /re-evaluate   — re-evaluate a golden record after enrichment
  GET  /health        — health check
  GET  /stats         — runtime statistics

v4: MCP integration. All tool calls (candidate evaluation, entity writing,
    knowledge graph) go through the remote MCP server via Streamable HTTP.
    Only the LLM client remains local (for ambiguous-case reasoning).
"""
from __future__ import annotations
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from config import load_config
from models.resolution import (
    ResolutionRequest, ResolutionResponse,
    ReEvaluationRequest, ReEvaluationResponse,
)
from clients.mcp_client import MCPToolClient
from clients.llm_client import LLMClient
from orchestrator import Orchestrator
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

# ── Global state ────────────────────────────────────────────
orchestrator: Orchestrator | None = None
_mcp: MCPToolClient | None = None
_llm: LLMClient | None = None
stats = {"requests": 0, "merges": 0, "creates": 0, "reviews": 0, "errors": 0, "start_time": 0}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wire all components on startup."""
    global orchestrator, _mcp, _llm
    stats["start_time"] = time.time()

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
    # The MCP server owns all data clients (MySQL, Milvus, GraphDB,
    # Embedding) and exposes them as tools. The agent only needs
    # a single connection to the MCP server.
    logger.info(f"Connecting to MCP Server at {cfg.mcp_server.url}...")
    mcp = MCPToolClient(url=cfg.mcp_server.url, timeout_ms=cfg.mcp_server.timeout_ms)
    await mcp.connect()
    _mcp = mcp

    # ── LLM stays local (not an MCP tool) ─────────────────
    llm = LLMClient(cfg.llm)
    await llm.connect()
    _llm = llm

    # ── Build orchestrator ────────────────────────────────
    orchestrator = Orchestrator(
        config=cfg,
        mcp=mcp,
        llm=llm,
    )

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


@app.post("/resolve", response_model=ResolutionResponse)
async def resolve(request: ResolutionRequest):
    """Resolve an orphan record: find matching golden record or create new."""
    if not orchestrator:
        raise HTTPException(503, "Agent not initialized")

    stats["requests"] += 1
    try:
        response = await orchestrator.resolve(request)
        if response.decision.value == "MERGE":
            stats["merges"] += 1
        elif response.decision.value == "NEW_ENTITY":
            stats["creates"] += 1
        elif response.decision.value == "REVIEW":
            stats["reviews"] += 1
        return response
    except Exception as e:
        stats["errors"] += 1
        logger.exception(f"Resolution failed for {request.record_id}: {e}")
        raise HTTPException(500, f"Resolution failed: {str(e)}")


@app.post("/re-evaluate", response_model=ReEvaluationResponse)
async def re_evaluate(request: ReEvaluationRequest):
    """Re-evaluate a golden record after enrichment added new bucket keys."""
    if not orchestrator:
        raise HTTPException(503, "Agent not initialized")

    stats["requests"] += 1
    try:
        return await orchestrator.re_evaluate(request)
    except Exception as e:
        stats["errors"] += 1
        logger.exception(f"Re-evaluation failed for {request.golden_record_id}: {e}")
        raise HTTPException(500, f"Re-evaluation failed: {str(e)}")


@app.get("/health")
async def health():
    components = {}
    if _mcp:
        components["mcp_server"] = "connected" if _mcp.connected else "disconnected"
        components["mcp_tools"] = len(_mcp._tool_names)
    if _llm:
        components["llm"] = "connected" if _llm.available else "unavailable"
    overall = "healthy" if orchestrator else "starting"
    return {
        "status": overall,
        "service": "entity-resolution-agent",
        "version": "4.0.0",
        "components": components,
    }


@app.get("/stats")
async def get_stats():
    uptime = time.time() - stats["start_time"] if stats["start_time"] else 0
    return {**stats, "uptime_seconds": int(uptime)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8085, reload=True)
