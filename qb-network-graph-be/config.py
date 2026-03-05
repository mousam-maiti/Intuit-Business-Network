"""
Config loader — .env -> YAML -> env var overrides.

Priority (highest first):
  1. Environment variables (MYSQL_HOST, etc.)
  2. be-config.yaml values
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
    val = os.environ.get(key)
    if val is None:
        return default
    if cast is bool:
        return val.lower() in ("true", "1", "yes")
    if cast is not None:
        return cast(val)
    return val


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8087


@dataclass
class MySQLConfig:
    host: str = "localhost"
    port: int = 3306
    user: str = "qb_admin"
    password: str = "qb_admin_pass"
    database: str = "quickbooks"
    pool_size: int = 5


@dataclass
class Neo4jConfig:
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "neo4j_pass"
    database: str = "neo4j"
    max_pool_size: int = 10


@dataclass
class EntityAgentConfig:
    url: str = "http://localhost:8085"
    timeout: int = 30


@dataclass
class FlinkSQLConfig:
    url: str = "http://localhost:8081"
    timeout: float = 30.0


@dataclass
class PaimonConfig:
    warehouse_path: str = "/Users/mousammaiti/IntuitQB-StreamHouse"


@dataclass
class SyncConfig:
    url: str = "http://localhost:8084"


@dataclass
class AppConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    mysql: MySQLConfig = field(default_factory=MySQLConfig)
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    entity_agent: EntityAgentConfig = field(default_factory=EntityAgentConfig)
    flink_sql: FlinkSQLConfig = field(default_factory=FlinkSQLConfig)
    paimon: PaimonConfig = field(default_factory=PaimonConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)


def _build(cls, data: dict):
    if data is None:
        return cls()
    flds = {f.name for f in cls.__dataclass_fields__.values()}
    return cls(**{k: v for k, v in data.items() if k in flds})


def load_config(path: str | None = None) -> AppConfig:
    if path is None:
        path = os.environ.get(
            "BE_CONFIG_PATH",
            str(Path(__file__).parent / "be-config.yaml"),
        )
    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    cfg = AppConfig(
        server=_build(ServerConfig, raw.get("server")),
        mysql=_build(MySQLConfig, raw.get("mysql")),
        neo4j=_build(Neo4jConfig, raw.get("neo4j")),
        entity_agent=_build(EntityAgentConfig, raw.get("entity_agent")),
        flink_sql=_build(FlinkSQLConfig, raw.get("flink_sql")),
        paimon=_build(PaimonConfig, raw.get("paimon")),
        sync=_build(SyncConfig, raw.get("sync")),
    )

    # Env var overrides
    cfg.server.host = _env("BE_HOST", cfg.server.host)
    cfg.server.port = _env("BE_PORT", cfg.server.port, int)

    cfg.mysql.host = _env("MYSQL_HOST", cfg.mysql.host)
    cfg.mysql.port = _env("MYSQL_PORT", cfg.mysql.port, int)
    cfg.mysql.user = _env("MYSQL_USER", cfg.mysql.user)
    cfg.mysql.password = _env("MYSQL_PASSWORD", cfg.mysql.password)
    cfg.mysql.database = _env("MYSQL_DATABASE", cfg.mysql.database)
    cfg.mysql.pool_size = _env("MYSQL_POOL_SIZE", cfg.mysql.pool_size, int)

    cfg.neo4j.uri = _env("NEO4J_URI", cfg.neo4j.uri)
    cfg.neo4j.user = _env("NEO4J_USER", cfg.neo4j.user)
    cfg.neo4j.password = _env("NEO4J_PASSWORD", cfg.neo4j.password)
    cfg.neo4j.database = _env("NEO4J_DATABASE", cfg.neo4j.database)
    cfg.neo4j.max_pool_size = _env("NEO4J_POOL_SIZE", cfg.neo4j.max_pool_size, int)

    cfg.entity_agent.url = _env("ENTITY_AGENT_URL", cfg.entity_agent.url)
    cfg.entity_agent.timeout = _env("ENTITY_AGENT_TIMEOUT", cfg.entity_agent.timeout, int)

    cfg.flink_sql.url = _env("FLINK_SQL_URL", cfg.flink_sql.url)
    cfg.flink_sql.timeout = _env("FLINK_SQL_TIMEOUT", cfg.flink_sql.timeout, float)

    cfg.paimon.warehouse_path = _env("PAIMON_WAREHOUSE_PATH", cfg.paimon.warehouse_path)

    cfg.sync.url = _env("SYNC_URL", cfg.sync.url)

    return cfg
