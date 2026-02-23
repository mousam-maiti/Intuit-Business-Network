"""
Conversational Agent Service — FastAPI + WebSocket + REST endpoints.

Endpoints:
  WS  /ws/{session_id}           — bidirectional chat
  GET  /health                    — component status
  GET  /sessions?user_id=         — list sessions
  POST /sessions?user_id=         — create session
  GET  /sessions/{id}/messages    — message history
  DELETE /sessions/{id}           — archive session
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager

import google.generativeai as genai
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config import load_config
from clients.mcp_client import MCPToolClient
from clients.chat_db import ChatDB, MockChatDB
from chat.session import SessionManager
from chat.context import ContextWindow
from chat.agent import ConversationalAgent
from chat.models import (
    WSClientMessage, WSSessionInfo, WSToolCall, WSResponse,
    WSError, WSContextCleared,
)

logging.basicConfig(
    level=os.environ.get("AGENT_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(name)-30s %(levelname)-5s %(message)s",
)
logger = logging.getLogger(__name__)

# ── Global state ────────────────────────────────────────────
_mcp: MCPToolClient | None = None
_db: ChatDB | MockChatDB | None = None
_session_mgr: SessionManager | None = None
_context_win: ContextWindow | None = None
_agent: ConversationalAgent | None = None
_cfg = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wire all components on startup."""
    global _mcp, _db, _session_mgr, _context_win, _agent, _cfg

    logger.info("Loading config...")
    _cfg = load_config()

    # ── Configure Gemini API ──────────────────────────────
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        genai.configure(api_key=api_key)
    else:
        logger.warning("GEMINI_API_KEY not set — LLM calls will fail")

    # ── Connect to MCP Server ────────────────────────────
    logger.info(f"Connecting to MCP Server at {_cfg.mcp_server.url}...")
    mcp = MCPToolClient(url=_cfg.mcp_server.url, timeout_ms=_cfg.mcp_server.timeout_ms)
    try:
        await mcp.connect()
        _mcp = mcp
    except Exception as e:
        logger.warning(f"MCP connection failed: {e} — agent will have limited functionality")
        _mcp = mcp  # keep ref for health check

    # ── Connect to MySQL ─────────────────────────────────
    db = ChatDB(
        host=_cfg.mysql.host, port=_cfg.mysql.port,
        user=_cfg.mysql.user, password=_cfg.mysql.password,
        database=_cfg.mysql.database, pool_size=_cfg.mysql.pool_size,
    )
    await db.connect()
    if not db.connected:
        logger.info("Using in-memory chat storage (MockChatDB)")
        db = MockChatDB()
        await db.connect()
    _db = db

    # ── Build components ─────────────────────────────────
    _session_mgr = SessionManager(_db)
    _context_win = ContextWindow(_db, _cfg.context)
    _agent = ConversationalAgent(
        mcp=mcp,
        llm_model=_cfg.llm.model,
        temperature=_cfg.llm.temperature,
        max_tool_calls=_cfg.context.max_tool_calls,
    )

    logger.info("=" * 60)
    logger.info("Conversational Agent Service READY")
    logger.info(f"  Port:       {_cfg.server.port}")
    logger.info(f"  MCP Server: {_cfg.mcp_server.url} ({'connected' if mcp.connected else 'FAILED'})")
    logger.info(f"  MCP Tools:  {len(mcp._tool_names)} available")
    logger.info(f"  MySQL:      {'connected' if _db.connected else 'in-memory fallback'}")
    logger.info(f"  LLM:        {_cfg.llm.model}")
    logger.info(f"  Context:    max={_cfg.context.max_messages} keep={_cfg.context.keep_recent}")
    logger.info("=" * 60)

    yield

    # ── Shutdown ──────────────────────────────────────────
    logger.info("Conversational agent shutting down...")
    if _mcp:
        await _mcp.close()
    if _db:
        await _db.close()
    logger.info("Conversational agent stopped.")


# ── FastAPI app ─────────────────────────────────────────────

app = FastAPI(
    title="QB Conversational Agent",
    description="WebSocket-based conversational AI for exploring the QB business network",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── WebSocket endpoint ──────────────────────────────────────

@app.websocket("/ws/{session_id}")
async def websocket_chat(ws: WebSocket, session_id: str, user_id: str = Query(default="anonymous")):
    """Bidirectional chat WebSocket."""
    await ws.accept()

    if not _session_mgr or not _agent or not _context_win:
        await ws.send_json(WSError(message="Agent not initialized").model_dump())
        await ws.close()
        return

    # Get or create session
    session = _session_mgr.get_or_create_session(session_id, user_id)

    # Send session info
    await ws.send_json(WSSessionInfo(
        session_id=session["session_id"],
        title=session.get("title"),
        message_count=session.get("message_count", 0),
    ).model_dump())

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json(WSError(message="Invalid JSON").model_dump())
                continue

            msg_type = data.get("type", "")

            if msg_type == "ping":
                await ws.send_json({"type": "pong"})
                continue

            if msg_type == "clear_context":
                _session_mgr.clear_session_context(session_id)
                session = _session_mgr.get_session(session_id)
                await ws.send_json(WSContextCleared(session_id=session_id).model_dump())
                continue

            if msg_type == "message":
                content = data.get("content", "").strip()
                if not content:
                    await ws.send_json(WSError(message="Empty message").model_dump())
                    continue

                ui_context = data.get("context")

                try:
                    # Save user message
                    _session_mgr.save_user_message(session_id, content, ui_context)

                    # Generate title on first message
                    session = _session_mgr.get_session(session_id)
                    if session.get("message_count", 0) == 1 and not session.get("title"):
                        try:
                            title = await _agent.generate_title(content)
                            _session_mgr.update_title(session_id, title)
                            session["title"] = title
                        except Exception as e:
                            logger.warning(f"Title generation failed: {e}")

                    # Assemble context
                    history = _context_win.assemble_context(session, content)

                    # Progress callback to stream tool events
                    async def on_tool_progress(tool_call: WSToolCall):
                        await ws.send_json(tool_call.model_dump())

                    # Process through agent
                    response = await _agent.handle_message(
                        session=session,
                        user_message=content,
                        ui_context=ui_context,
                        history=history,
                        progress_callback=on_tool_progress,
                    )

                    # Save assistant response
                    _session_mgr.save_assistant_message(
                        session_id, response.content,
                        metadata={"has_chart": response.chart is not None,
                                  "has_table": response.table is not None},
                    )

                    # Send response
                    await ws.send_json(response.model_dump(exclude_none=True))

                    # Maybe compress context
                    session = _session_mgr.get_session(session_id)
                    await _context_win.maybe_compress(session, _cfg.llm.model)

                except Exception as e:
                    logger.exception(f"Error processing message: {e}")
                    await ws.send_json(WSError(message=f"Processing error: {str(e)}").model_dump())

                continue

            await ws.send_json(WSError(message=f"Unknown message type: {msg_type}").model_dump())

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: session={session_id} user={user_id}")


# ── REST endpoints ──────────────────────────────────────────

@app.get("/health")
async def health():
    components = {}
    if _mcp:
        components["mcp_server"] = "connected" if _mcp.connected else "disconnected"
        components["mcp_tools"] = len(_mcp._tool_names)
    if _db:
        components["mysql"] = "connected" if _db.connected else "in-memory"
    components["llm"] = _cfg.llm.model if _cfg else "unknown"

    overall = "healthy" if _agent else "starting"
    return {
        "status": overall,
        "service": "conversational-agent",
        "version": "1.0.0",
        "components": components,
    }


@app.get("/sessions")
async def list_sessions(user_id: str = Query(...)):
    if not _session_mgr:
        raise HTTPException(503, "Agent not initialized")
    sessions = _session_mgr.list_user_sessions(user_id)
    # Serialize datetimes
    for s in sessions:
        for key in ("created_at", "updated_at"):
            if s.get(key) and hasattr(s[key], "isoformat"):
                s[key] = s[key].isoformat()
    return {"data": sessions, "total": len(sessions)}


@app.post("/sessions")
async def create_session(user_id: str = Query(...)):
    if not _session_mgr:
        raise HTTPException(503, "Agent not initialized")
    session_id = str(uuid.uuid4())
    session = _session_mgr.get_or_create_session(session_id, user_id)
    for key in ("created_at", "updated_at"):
        if session.get(key) and hasattr(session[key], "isoformat"):
            session[key] = session[key].isoformat()
    return {"data": session}


@app.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, limit: int = Query(default=100)):
    if not _session_mgr:
        raise HTTPException(503, "Agent not initialized")
    session = _session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    messages = _session_mgr.get_session_messages(session_id, limit=limit)
    for m in messages:
        if m.get("created_at") and hasattr(m["created_at"], "isoformat"):
            m["created_at"] = m["created_at"].isoformat()
    return {"data": messages, "total": len(messages)}


@app.delete("/sessions/{session_id}")
async def archive_session(session_id: str):
    if not _session_mgr:
        raise HTTPException(503, "Agent not initialized")
    session = _session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    _session_mgr.archive_session(session_id)
    return {"data": {"session_id": session_id, "status": "archived"}}


if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run("main:app", host=cfg.server.host, port=cfg.server.port, reload=True)
