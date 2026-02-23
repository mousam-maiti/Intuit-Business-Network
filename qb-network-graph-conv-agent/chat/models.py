"""
Pydantic models for chat sessions, messages, and WebSocket protocol.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Database models ─────────────────────────────────────────

class SessionStatus(str, Enum):
    active = "active"
    archived = "archived"


class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class ChatSession(BaseModel):
    session_id: str
    user_id: str
    title: Optional[str] = None
    context_summary: Optional[str] = None
    compressed_up_to: int = 0
    message_count: int = 0
    status: SessionStatus = SessionStatus.active
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChatMessage(BaseModel):
    message_id: str
    session_id: str
    role: MessageRole
    content: str
    metadata: Optional[Dict[str, Any]] = None
    token_estimate: int = 0
    created_at: Optional[datetime] = None


# ── WebSocket protocol — Client → Server ───────────────────

class WSClientMessage(BaseModel):
    type: str  # "message" | "clear_context" | "ping"
    content: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


# ── WebSocket protocol — Server → Client ───────────────────

class WSSessionInfo(BaseModel):
    type: str = "session_info"
    session_id: str
    title: Optional[str] = None
    message_count: int = 0


class WSToolCall(BaseModel):
    type: str = "tool_call"
    name: str
    status: str = "running"  # "running" | "done" | "error"
    label: str = ""
    result_preview: Optional[str] = None


class AITable(BaseModel):
    headers: List[str]
    rows: List[List[str]]


class AIChart(BaseModel):
    type: str  # "bar" | "area" | "pie"
    title: str = ""
    data: List[Dict[str, Any]]
    config: Optional[Dict[str, Any]] = None


class AIScore(BaseModel):
    label: str
    value: float


class AISignal(BaseModel):
    icon: str  # "positive" | "negative" | "neutral"
    text: str


class AIAction(BaseModel):
    label: str
    action: str  # "navigate" | "select_entity" | "ask"
    payload: Dict[str, Any] = Field(default_factory=dict)


class WSResponse(BaseModel):
    type: str = "response"
    content: str = ""
    entities: Optional[List[str]] = None
    table: Optional[AITable] = None
    chart: Optional[AIChart] = None
    scores: Optional[List[AIScore]] = None
    signals: Optional[List[AISignal]] = None
    actions: Optional[List[AIAction]] = None
    followup: Optional[str] = None


class WSError(BaseModel):
    type: str = "error"
    message: str


class WSContextCleared(BaseModel):
    type: str = "context_cleared"
    session_id: str
