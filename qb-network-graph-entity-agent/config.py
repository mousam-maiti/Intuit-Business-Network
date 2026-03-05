"""
Config loader — .env → YAML → env var overrides.

Priority (highest first):
  1. Environment variables (THRESHOLD_AUTO_MERGE, MYSQL_HOST, etc.)
  2. agent-config.yaml values
  3. Dataclass defaults

v3 changes:
  - Added MySQLConfig (golden record source of truth)
  - RedisConfig kept but optional (Tier 2 read cache)
  - PaimonConfig kept for pipeline reads (entity_connections)
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
class Thresholds:
    auto_merge: float = 0.82        # was 0.85 — safe with identity floor cap
    human_review: float = 0.55      # was 0.60 — widen deterministic zone
    new_entity: float = 0.55        # was 0.60
    embedding_needed_low: float = 0.45  # was 0.40 — skip more embedding calls
    embedding_needed_high: float = 0.82 # was 0.85 — match new auto_merge
    min_identity_score: float = 0.75    # name gate — below this, auto-create new entity


@dataclass
class Weights:
    identity: float = 0.50    # was 0.35 — highest priority (Name/EIN)
    industry: float = 0.20    # was 0.25
    location: float = 0.12    # was 0.15
    commodity: float = 0.10   # was 0.15
    behavioral: float = 0.08  # was 0.10

    def as_dict(self) -> dict[str, float]:
        return {
            "identity": self.identity, "industry": self.industry,
            "location": self.location, "commodity": self.commodity,
            "behavioral": self.behavioral,
        }


@dataclass
class ReEvaluation:
    max_chain_depth: int = 3
    force_review_at_depth: int = 3


@dataclass
class LLMConfig:
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"
    ambiguous_model: str = "gemini-2.5-pro"
    max_tokens: int = 1024
    temperature: float = 0.0
    timeout_ms: int = 10000
    fallback_decision: str = "REVIEW"


@dataclass
class EmbeddingConfig:
    provider: str = "gemini"
    model: str = "text-embedding-004"
    dimension: int = 768
    task_type: str = "SEMANTIC_SIMILARITY"
    batch_size: int = 10
    fallback_provider: str = "local"
    fallback_model: str = "all-MiniLM-L6-v2"
    fallback_dimension: int = 384


@dataclass
class KnowledgeGraphConfig:
    sparql_endpoint: str = "http://localhost:7200/repositories/qb-ontology"
    update_endpoint: str = "http://localhost:7200/repositories/qb-ontology/statements"
    timeout_ms: int = 2000
    max_concurrent_queries: int = 2
    direct_write: bool = True
    fallback_to_changelog: bool = True
    t_box_cache_ttl_hours: int = 24


@dataclass
class MySQLConfig:
    """MySQL — golden record source of truth.

    Agent writes: golden_records, relationships, resolution_audit, pending_resolution.
    Agent reads: golden_records (find_candidates via indexed queries).
    """
    host: str = "localhost"
    port: int = 3306
    user: str = "qb_admin"
    password: str = "qb_admin_pass"
    database: str = "quickbooks"
    pool_size: int = 5


@dataclass
class RedisConfig:
    """Redis — Tier 2 read cache (NOT in write path).

    If enabled, used as cache-aside for hot golden records.
    Not required for Tier 1 deployment.
    """
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    decode_responses: bool = True
    socket_timeout: int = 2
    enabled: bool = False  # Tier 2 — disabled by default


@dataclass
class PaimonConfig:
    """Paimon — pipeline data only (bronze CDC, silver entity_connections).

    Agent does NOT write golden records to Paimon (that's MySQL now).
    PaimonConfig kept for classifier-orchestrator reads and source lineage.
    """
    warehouse: str = "/tmp/paimon-warehouse"
    catalog_type: str = "filesystem"
    database: str = "entity_resolution"
    bucket_count: int = 2
    write_queue_size: int = 1000
    max_workers: int = 4


@dataclass
class MCPConfig:
    """MCP Server connection — replaces direct class instantiation of
    CandidateEvaluator, KnowledgeGraphServer, EntityWriter."""
    url: str = "http://localhost:8081/mcp"
    timeout_ms: int = 30000


@dataclass
class BucketConfig:
    max_commodity_keywords: int = 3


@dataclass
class TelemetryConfig:
    enabled: bool = True
    service_name: str = "qb-entity-resolution-agent"
    otlp_endpoint: str = "http://localhost:4317"
    export_interval_ms: int = 15000


@dataclass
class AgentConfig:
    thresholds: Thresholds = field(default_factory=Thresholds)
    weights: Weights = field(default_factory=Weights)
    re_evaluation: ReEvaluation = field(default_factory=ReEvaluation)
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    knowledge_graph: KnowledgeGraphConfig = field(default_factory=KnowledgeGraphConfig)
    mysql: MySQLConfig = field(default_factory=MySQLConfig)
    mcp_server: MCPConfig = field(default_factory=MCPConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    paimon: PaimonConfig = field(default_factory=PaimonConfig)
    buckets: BucketConfig = field(default_factory=BucketConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)


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

    bkt = raw.get("buckets", {})
    max_kw = bkt.get("max_commodity_keywords", 3)
    tel_raw = raw.get("telemetry", {})

    cfg = AgentConfig(
        thresholds=_build(Thresholds, raw.get("thresholds")),
        weights=_build(Weights, raw.get("weights")),
        re_evaluation=_build(ReEvaluation, raw.get("re_evaluation")),
        llm=_build(LLMConfig, raw.get("llm")),
        embedding=_build(EmbeddingConfig, raw.get("embedding")),
        knowledge_graph=_build(KnowledgeGraphConfig, raw.get("knowledge_graph")),
        mysql=_build(MySQLConfig, raw.get("mysql")),
        mcp_server=_build(MCPConfig, raw.get("mcp_server")),
        redis=_build(RedisConfig, raw.get("redis")),
        paimon=_build(PaimonConfig, raw.get("paimon")),
        buckets=BucketConfig(max_commodity_keywords=max_kw),
        telemetry=_build(TelemetryConfig, tel_raw if isinstance(tel_raw, dict) else {}),
    )

    # ── Env var overrides ────────────────────────────────────

    # Thresholds
    cfg.thresholds.auto_merge = _env("THRESHOLD_AUTO_MERGE", cfg.thresholds.auto_merge, float)
    cfg.thresholds.human_review = _env("THRESHOLD_HUMAN_REVIEW", cfg.thresholds.human_review, float)
    cfg.thresholds.new_entity = _env("THRESHOLD_NEW_ENTITY", cfg.thresholds.new_entity, float)
    cfg.thresholds.embedding_needed_low = _env("THRESHOLD_EMBEDDING_LOW", cfg.thresholds.embedding_needed_low, float)
    cfg.thresholds.embedding_needed_high = _env("THRESHOLD_EMBEDDING_HIGH", cfg.thresholds.embedding_needed_high, float)
    cfg.thresholds.min_identity_score = _env("THRESHOLD_MIN_IDENTITY", cfg.thresholds.min_identity_score, float)

    # Weights
    cfg.weights.identity = _env("WEIGHT_IDENTITY", cfg.weights.identity, float)
    cfg.weights.industry = _env("WEIGHT_INDUSTRY", cfg.weights.industry, float)
    cfg.weights.location = _env("WEIGHT_LOCATION", cfg.weights.location, float)
    cfg.weights.commodity = _env("WEIGHT_COMMODITY", cfg.weights.commodity, float)
    cfg.weights.behavioral = _env("WEIGHT_BEHAVIORAL", cfg.weights.behavioral, float)

    # Re-evaluation
    cfg.re_evaluation.max_chain_depth = _env("RE_EVAL_MAX_CHAIN_DEPTH", cfg.re_evaluation.max_chain_depth, int)
    cfg.re_evaluation.force_review_at_depth = _env("RE_EVAL_FORCE_REVIEW_AT_DEPTH", cfg.re_evaluation.force_review_at_depth, int)

    # LLM
    cfg.llm.provider = _env("LLM_PROVIDER", cfg.llm.provider)
    cfg.llm.model = _env("LLM_MODEL", cfg.llm.model)
    cfg.llm.ambiguous_model = _env("LLM_AMBIGUOUS_MODEL", cfg.llm.ambiguous_model)
    cfg.llm.max_tokens = _env("LLM_MAX_TOKENS", cfg.llm.max_tokens, int)
    cfg.llm.temperature = _env("LLM_TEMPERATURE", cfg.llm.temperature, float)
    cfg.llm.timeout_ms = _env("LLM_TIMEOUT_MS", cfg.llm.timeout_ms, int)
    cfg.llm.fallback_decision = _env("LLM_FALLBACK_DECISION", cfg.llm.fallback_decision)

    # Embedding
    cfg.embedding.provider = _env("EMBEDDING_PROVIDER", cfg.embedding.provider)
    cfg.embedding.model = _env("EMBEDDING_MODEL", cfg.embedding.model)
    cfg.embedding.dimension = _env("EMBEDDING_DIMENSION", cfg.embedding.dimension, int)
    cfg.embedding.task_type = _env("EMBEDDING_TASK_TYPE", cfg.embedding.task_type)
    cfg.embedding.batch_size = _env("EMBEDDING_BATCH_SIZE", cfg.embedding.batch_size, int)

    # MySQL
    cfg.mysql.host = _env("MYSQL_HOST", cfg.mysql.host)
    cfg.mysql.port = _env("MYSQL_PORT", cfg.mysql.port, int)
    cfg.mysql.user = _env("MYSQL_USER", cfg.mysql.user)
    cfg.mysql.password = _env("MYSQL_PASSWORD", cfg.mysql.password)
    cfg.mysql.database = _env("MYSQL_DATABASE", cfg.mysql.database)
    cfg.mysql.pool_size = _env("MYSQL_POOL_SIZE", cfg.mysql.pool_size, int)

    # MCP Server
    cfg.mcp_server.url = _env("MCP_SERVER_URL", cfg.mcp_server.url)
    cfg.mcp_server.timeout_ms = _env("MCP_SERVER_TIMEOUT_MS", cfg.mcp_server.timeout_ms, int)

    # Redis (Tier 2 — optional)
    cfg.redis.host = _env("REDIS_HOST", cfg.redis.host)
    cfg.redis.port = _env("REDIS_PORT", cfg.redis.port, int)
    cfg.redis.db = _env("REDIS_DB", cfg.redis.db, int)
    cfg.redis.enabled = _env("REDIS_ENABLED", cfg.redis.enabled, bool)

    # Knowledge Graph
    cfg.knowledge_graph.sparql_endpoint = _env("KG_SPARQL_ENDPOINT", cfg.knowledge_graph.sparql_endpoint)
    cfg.knowledge_graph.update_endpoint = _env("KG_UPDATE_ENDPOINT", cfg.knowledge_graph.update_endpoint)
    cfg.knowledge_graph.timeout_ms = _env("KG_TIMEOUT_MS", cfg.knowledge_graph.timeout_ms, int)

    # Paimon (pipeline reads only)
    cfg.paimon.warehouse = _env("PAIMON_WAREHOUSE", cfg.paimon.warehouse)

    # Buckets
    cfg.buckets.max_commodity_keywords = _env("BUCKET_MAX_COMMODITY_KEYWORDS", cfg.buckets.max_commodity_keywords, int)

    # Telemetry
    cfg.telemetry.enabled = _env("OTEL_ENABLED", cfg.telemetry.enabled, bool)
    cfg.telemetry.service_name = _env("OTEL_SERVICE_NAME", cfg.telemetry.service_name)
    cfg.telemetry.otlp_endpoint = _env("OTEL_EXPORTER_OTLP_ENDPOINT", cfg.telemetry.otlp_endpoint)

    return cfg
