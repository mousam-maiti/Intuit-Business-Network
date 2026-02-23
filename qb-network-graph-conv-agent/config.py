"""
Config loader — .env → YAML → env var overrides.

Priority (highest first):
  1. Environment variables
  2. agent-config.yaml values
  3. Dataclass defaults
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass


def _env(key: str, default=None, cast=None):
    """Read env var with optional type cast."""
    val = os.environ.get(key)
    if val is None:
        return default
    if cast is bool:
        return val.lower() in ("true", "1", "yes")
    if cast is not None:
        return cast(val)
    return val


# ── Dataclasses ─────────────────────────────────────────────

@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8082


@dataclass
class MCPConfig:
    url: str = "http://localhost:8081/mcp"
    timeout_ms: int = 30000


@dataclass
class LLMConfig:
    model: str = "gemini-2.5-flash"
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout_ms: int = 30000


@dataclass
class MySQLConfig:
    host: str = "localhost"
    port: int = 3306
    user: str = "qb_admin"
    password: str = "qb_admin_pass"
    database: str = "quickbooks"
    pool_size: int = 5


@dataclass
class ContextConfig:
    max_messages: int = 30
    keep_recent: int = 10
    max_tool_calls: int = 5


@dataclass
class AgentConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    mcp_server: MCPConfig = field(default_factory=MCPConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    mysql: MySQLConfig = field(default_factory=MySQLConfig)
    context: ContextConfig = field(default_factory=ContextConfig)


# ── Loader ──────────────────────────────────────────────────

def _build(cls, data: dict):
    """Build dataclass from dict, ignoring unknown keys."""
    if data is None:
        return cls()
    flds = {f.name for f in cls.__dataclass_fields__.values()}
    return cls(**{k: v for k, v in data.items() if k in flds})


def load_config(path: str | None = None) -> AgentConfig:
    """Load config: YAML base → env var overrides."""
    if path is None:
        path = os.environ.get(
            "AGENT_CONFIG_PATH",
            str(Path(__file__).parent / "agent-config.yaml"),
        )
    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    cfg = AgentConfig(
        server=_build(ServerConfig, raw.get("server")),
        mcp_server=_build(MCPConfig, raw.get("mcp_server")),
        llm=_build(LLMConfig, raw.get("llm")),
        mysql=_build(MySQLConfig, raw.get("mysql")),
        context=_build(ContextConfig, raw.get("context")),
    )

    # ── Env var overrides ────────────────────────────────────
    cfg.server.host = _env("SERVER_HOST", cfg.server.host)
    cfg.server.port = _env("SERVER_PORT", cfg.server.port, int)

    cfg.mcp_server.url = _env("MCP_SERVER_URL", cfg.mcp_server.url)
    cfg.mcp_server.timeout_ms = _env("MCP_SERVER_TIMEOUT_MS", cfg.mcp_server.timeout_ms, int)

    cfg.llm.model = _env("LLM_MODEL", cfg.llm.model)
    cfg.llm.temperature = _env("LLM_TEMPERATURE", cfg.llm.temperature, float)
    cfg.llm.max_tokens = _env("LLM_MAX_TOKENS", cfg.llm.max_tokens, int)
    cfg.llm.timeout_ms = _env("LLM_TIMEOUT_MS", cfg.llm.timeout_ms, int)

    cfg.mysql.host = _env("MYSQL_HOST", cfg.mysql.host)
    cfg.mysql.port = _env("MYSQL_PORT", cfg.mysql.port, int)
    cfg.mysql.user = _env("MYSQL_USER", cfg.mysql.user)
    cfg.mysql.password = _env("MYSQL_PASSWORD", cfg.mysql.password)
    cfg.mysql.database = _env("MYSQL_DATABASE", cfg.mysql.database)
    cfg.mysql.pool_size = _env("MYSQL_POOL_SIZE", cfg.mysql.pool_size, int)

    cfg.context.max_messages = _env("CONTEXT_MAX_MESSAGES", cfg.context.max_messages, int)
    cfg.context.keep_recent = _env("CONTEXT_KEEP_RECENT", cfg.context.keep_recent, int)
    cfg.context.max_tool_calls = _env("CONTEXT_MAX_TOOL_CALLS", cfg.context.max_tool_calls, int)

    return cfg
