"""
Config loader — .env → YAML → env var overrides.

Priority (highest first):
  1. Environment variables (THRESHOLD_AUTO_MERGE, MYSQL_HOST, etc.)
  2. server-config.yaml values
  3. Dataclass defaults

Adapted from entity agent config.py. Adds ServerConfig for MCP server settings.
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
    """MCP server transport settings."""
    host: str = "0.0.0.0"
    port: int = 8081
    name: str = "qb-network-graph-mcp"


@dataclass
class Thresholds:
    auto_merge: float = 0.85
    human_review: float = 0.60
    new_entity: float = 0.60
    embedding_needed_low: float = 0.40
    embedding_needed_high: float = 0.85


@dataclass
class Weights:
    identity: float = 0.45
    industry: float = 0.20
    location: float = 0.15
    commodity: float = 0.10
    behavioral: float = 0.10

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
    model: str = "gemini-2.5-pro"
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
class MySQLConfig:
    """MySQL — golden record source of truth."""
    host: str = "localhost"
    port: int = 3306
    user: str = "qb_admin"
    password: str = "qb_admin_pass"
    database: str = "quickbooks"
    pool_size: int = 5


@dataclass
class MilvusConfig:
    """Milvus — vector search for intuitive UI search."""
    host: str = "localhost"
    port: int = 19530
    gemini_api_key: str = ""


@dataclass
class Neo4jConfig:
    """Neo4j — directed graph traversal for supply chain paths."""
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "neo4j_pass"
    database: str = "neo4j"
    max_pool_size: int = 50


@dataclass
class RedisConfig:
    """Redis — hot subgraph caching with TTL-based invalidation."""
    host: str = "localhost"
    port: int = 6379
    password: str = ""
    db: int = 0
    default_ttl: int = 3600


@dataclass
class BucketConfig:
    max_commodity_keywords: int = 3


@dataclass
class AgentConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    thresholds: Thresholds = field(default_factory=Thresholds)
    weights: Weights = field(default_factory=Weights)
    re_evaluation: ReEvaluation = field(default_factory=ReEvaluation)
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    mysql: MySQLConfig = field(default_factory=MySQLConfig)
    milvus: MilvusConfig = field(default_factory=MilvusConfig)
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    buckets: BucketConfig = field(default_factory=BucketConfig)


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
            "MCP_CONFIG_PATH",
            str(Path(__file__).parent / "server-config.yaml"),
        )
    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    bkt = raw.get("buckets", {})
    max_kw = bkt.get("max_commodity_keywords", 3)

    cfg = AgentConfig(
        server=_build(ServerConfig, raw.get("server")),
        thresholds=_build(Thresholds, raw.get("thresholds")),
        weights=_build(Weights, raw.get("weights")),
        re_evaluation=_build(ReEvaluation, raw.get("re_evaluation")),
        llm=_build(LLMConfig, raw.get("llm")),
        embedding=_build(EmbeddingConfig, raw.get("embedding")),
        mysql=_build(MySQLConfig, raw.get("mysql")),
        milvus=_build(MilvusConfig, raw.get("milvus")),
        neo4j=_build(Neo4jConfig, raw.get("neo4j")),
        redis=_build(RedisConfig, raw.get("redis")),
        buckets=BucketConfig(max_commodity_keywords=max_kw),
    )

    # ── Env var overrides ────────────────────────────────────

    # Server
    cfg.server.host = _env("MCP_SERVER_HOST", cfg.server.host)
    cfg.server.port = _env("MCP_SERVER_PORT", cfg.server.port, int)

    # Thresholds
    cfg.thresholds.auto_merge = _env("THRESHOLD_AUTO_MERGE", cfg.thresholds.auto_merge, float)
    cfg.thresholds.human_review = _env("THRESHOLD_HUMAN_REVIEW", cfg.thresholds.human_review, float)
    cfg.thresholds.new_entity = _env("THRESHOLD_NEW_ENTITY", cfg.thresholds.new_entity, float)
    cfg.thresholds.embedding_needed_low = _env("THRESHOLD_EMBEDDING_LOW", cfg.thresholds.embedding_needed_low, float)
    cfg.thresholds.embedding_needed_high = _env("THRESHOLD_EMBEDDING_HIGH", cfg.thresholds.embedding_needed_high, float)

    # Weights
    cfg.weights.identity = _env("WEIGHT_IDENTITY", cfg.weights.identity, float)
    cfg.weights.industry = _env("WEIGHT_INDUSTRY", cfg.weights.industry, float)
    cfg.weights.location = _env("WEIGHT_LOCATION", cfg.weights.location, float)
    cfg.weights.commodity = _env("WEIGHT_COMMODITY", cfg.weights.commodity, float)
    cfg.weights.behavioral = _env("WEIGHT_BEHAVIORAL", cfg.weights.behavioral, float)

    # LLM
    cfg.llm.provider = _env("LLM_PROVIDER", cfg.llm.provider)
    cfg.llm.model = _env("LLM_MODEL", cfg.llm.model)
    cfg.llm.ambiguous_model = _env("LLM_AMBIGUOUS_MODEL", cfg.llm.ambiguous_model)
    cfg.llm.max_tokens = _env("LLM_MAX_TOKENS", cfg.llm.max_tokens, int)
    cfg.llm.temperature = _env("LLM_TEMPERATURE", cfg.llm.temperature, float)
    cfg.llm.timeout_ms = _env("LLM_TIMEOUT_MS", cfg.llm.timeout_ms, int)

    # Embedding
    cfg.embedding.provider = _env("EMBEDDING_PROVIDER", cfg.embedding.provider)
    cfg.embedding.model = _env("EMBEDDING_MODEL", cfg.embedding.model)
    cfg.embedding.dimension = _env("EMBEDDING_DIMENSION", cfg.embedding.dimension, int)

    # MySQL
    cfg.mysql.host = _env("MYSQL_HOST", cfg.mysql.host)
    cfg.mysql.port = _env("MYSQL_PORT", cfg.mysql.port, int)
    cfg.mysql.user = _env("MYSQL_USER", cfg.mysql.user)
    cfg.mysql.password = _env("MYSQL_PASSWORD", cfg.mysql.password)
    cfg.mysql.database = _env("MYSQL_DATABASE", cfg.mysql.database)
    cfg.mysql.pool_size = _env("MYSQL_POOL_SIZE", cfg.mysql.pool_size, int)

    # Milvus
    cfg.milvus.host = _env("MILVUS_HOST", cfg.milvus.host)
    cfg.milvus.port = _env("MILVUS_PORT", cfg.milvus.port, int)
    cfg.milvus.gemini_api_key = _env("GEMINI_API_KEY", cfg.milvus.gemini_api_key)

    # Neo4j
    cfg.neo4j.uri = _env("NEO4J_URI", cfg.neo4j.uri)
    cfg.neo4j.user = _env("NEO4J_USER", cfg.neo4j.user)
    cfg.neo4j.password = _env("NEO4J_PASSWORD", cfg.neo4j.password)
    cfg.neo4j.database = _env("NEO4J_DATABASE", cfg.neo4j.database)
    cfg.neo4j.max_pool_size = _env("NEO4J_MAX_POOL_SIZE", cfg.neo4j.max_pool_size, int)

    # Redis
    cfg.redis.host = _env("REDIS_HOST", cfg.redis.host)
    cfg.redis.port = _env("REDIS_PORT", cfg.redis.port, int)
    cfg.redis.password = _env("REDIS_PASSWORD", cfg.redis.password)
    cfg.redis.db = _env("REDIS_DB", cfg.redis.db, int)
    cfg.redis.default_ttl = _env("REDIS_DEFAULT_TTL", cfg.redis.default_ttl, int)

    # Buckets
    cfg.buckets.max_commodity_keywords = _env("BUCKET_MAX_COMMODITY_KEYWORDS", cfg.buckets.max_commodity_keywords, int)

    return cfg
