from __future__ import annotations

"""Health and stats routes: GET /health, GET /stats."""
import time

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    mcp = getattr(request.app.state, "mcp_client", None)
    llm_reasoner = getattr(request.app.state, "llm_reasoner", None)
    resolution_svc = getattr(request.app.state, "resolution_service", None)

    components = {}
    if mcp:
        components["mcp_server"] = "connected" if mcp.connected else "disconnected"
        components["mcp_tools"] = len(mcp._tool_names)
    if llm_reasoner:
        components["llm"] = "connected" if llm_reasoner.available else "unavailable"
    cfg = getattr(request.app.state, "cfg", None)
    if cfg:
        components["llm_provider"] = cfg.llm.provider
        components["llm_model"] = cfg.llm.model
        components["embedding_provider"] = cfg.embedding.provider
        components["embedding_model"] = cfg.embedding.model

    overall = "healthy" if resolution_svc else "starting"
    return {
        "status": overall,
        "service": "entity-resolution-agent",
        "version": "4.0.0",
        "components": components,
    }


@router.get("/stats")
async def get_stats(request: Request):
    stats = getattr(request.app.state, "stats", {})
    uptime = time.time() - stats.get("start_time", 0) if stats.get("start_time") else 0
    return {**stats, "uptime_seconds": int(uptime)}
