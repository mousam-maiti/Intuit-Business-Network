"""Tests for config.py — config loading, env var overrides, _build helper."""
import os
import pytest
import tempfile
import yaml
from config import (
    _env, _build, load_config,
    ServerConfig, Thresholds, Weights, MySQLConfig,
    AgentConfig, LLMConfig, EmbeddingConfig, Neo4jConfig, RedisConfig,
    BucketConfig, ReEvaluation,
)


class TestEnvHelper:
    def test_env_present(self, monkeypatch):
        monkeypatch.setenv("TEST_KEY", "hello")
        assert _env("TEST_KEY") == "hello"

    def test_env_missing_returns_default(self):
        assert _env("NONEXISTENT_KEY_12345", "default_val") == "default_val"

    def test_env_missing_returns_none(self):
        assert _env("NONEXISTENT_KEY_12345") is None

    def test_env_cast_int(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "42")
        assert _env("TEST_INT", cast=int) == 42

    def test_env_cast_float(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "3.14")
        assert _env("TEST_FLOAT", cast=float) == pytest.approx(3.14)

    def test_env_cast_bool_true(self, monkeypatch):
        for val in ("true", "1", "yes"):
            monkeypatch.setenv("TEST_BOOL", val)
            assert _env("TEST_BOOL", cast=bool) is True

    def test_env_cast_bool_false(self, monkeypatch):
        for val in ("false", "0", "no", "anything_else"):
            monkeypatch.setenv("TEST_BOOL", val)
            assert _env("TEST_BOOL", cast=bool) is False


class TestBuildHelper:
    def test_none_returns_default(self):
        result = _build(ServerConfig, None)
        assert result.host == "0.0.0.0"
        assert result.port == 8081

    def test_empty_dict_returns_default(self):
        result = _build(ServerConfig, {})
        assert result.host == "0.0.0.0"

    def test_valid_data(self):
        result = _build(ServerConfig, {"host": "127.0.0.1", "port": 9090})
        assert result.host == "127.0.0.1"
        assert result.port == 9090

    def test_unknown_keys_ignored(self):
        result = _build(ServerConfig, {"host": "127.0.0.1", "unknown_key": "ignored"})
        assert result.host == "127.0.0.1"

    def test_partial_data(self):
        result = _build(ServerConfig, {"port": 9999})
        assert result.host == "0.0.0.0"  # default
        assert result.port == 9999


class TestDataclassDefaults:
    def test_server_config(self):
        c = ServerConfig()
        assert c.host == "0.0.0.0"
        assert c.port == 8081
        assert c.name == "qb-network-graph-mcp"

    def test_thresholds(self):
        t = Thresholds()
        assert t.auto_merge == 0.85
        assert t.human_review == 0.60
        assert t.new_entity == 0.60

    def test_weights(self):
        w = Weights()
        assert w.identity == 0.45
        assert w.industry == 0.20
        assert w.location == 0.15
        assert w.commodity == 0.10
        assert w.behavioral == 0.10

    def test_weights_as_dict(self):
        w = Weights()
        d = w.as_dict()
        assert d == {"identity": 0.45, "industry": 0.20, "location": 0.15,
                     "commodity": 0.10, "behavioral": 0.10}
        assert abs(sum(d.values()) - 1.0) < 0.001

    def test_mysql_config(self):
        c = MySQLConfig()
        assert c.host == "localhost"
        assert c.port == 3306

    def test_neo4j_config(self):
        c = Neo4jConfig()
        assert c.uri == "bolt://localhost:7687"
        assert c.user == "neo4j"
        assert c.password == "neo4j_pass"
        assert c.database == "neo4j"
        assert c.max_pool_size == 50

    def test_redis_config(self):
        c = RedisConfig()
        assert c.host == "localhost"
        assert c.port == 6379
        assert c.db == 0
        assert c.default_ttl == 3600

    def test_llm_config(self):
        c = LLMConfig()
        assert c.provider == "gemini"
        assert c.fallback_decision == "REVIEW"

    def test_embedding_config(self):
        c = EmbeddingConfig()
        assert c.dimension == 768

    def test_agent_config(self):
        c = AgentConfig()
        assert isinstance(c.server, ServerConfig)
        assert isinstance(c.thresholds, Thresholds)
        assert isinstance(c.weights, Weights)
        assert isinstance(c.mysql, MySQLConfig)
        assert isinstance(c.neo4j, Neo4jConfig)
        assert isinstance(c.redis, RedisConfig)


class TestLoadConfig:
    # Env vars loaded from .env override YAML; clear them for YAML-only tests.
    _ENV_OVERRIDES = [
        "MCP_SERVER_HOST", "MCP_SERVER_PORT", "MYSQL_HOST", "MYSQL_PORT",
        "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE",
        "GEMINI_API_KEY", "THRESHOLD_AUTO_MERGE",
    ]

    def _clear_env(self, monkeypatch):
        for key in self._ENV_OVERRIDES:
            monkeypatch.delenv(key, raising=False)

    def test_loads_from_yaml(self, tmp_path, monkeypatch):
        self._clear_env(monkeypatch)
        config_data = {
            "server": {"host": "127.0.0.1", "port": 9999},
            "thresholds": {"auto_merge": 0.90},
            "weights": {"identity": 0.40},
            "mysql": {"host": "db.example.com", "port": 3307},
            "buckets": {"max_commodity_keywords": 5},
        }
        config_file = tmp_path / "test-config.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = load_config(str(config_file))
        assert cfg.server.host == "127.0.0.1"
        assert cfg.server.port == 9999
        assert cfg.thresholds.auto_merge == 0.90
        assert cfg.weights.identity == 0.40
        assert cfg.mysql.host == "db.example.com"
        assert cfg.buckets.max_commodity_keywords == 5

    def test_empty_yaml(self, tmp_path, monkeypatch):
        self._clear_env(monkeypatch)
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")
        cfg = load_config(str(config_file))
        # All defaults
        assert cfg.server.port == 8081
        assert cfg.thresholds.auto_merge == 0.85

    def test_env_var_overrides_yaml(self, tmp_path, monkeypatch):
        config_data = {"server": {"port": 8081}}
        config_file = tmp_path / "test-config.yaml"
        config_file.write_text(yaml.dump(config_data))

        monkeypatch.setenv("MCP_SERVER_PORT", "9999")
        monkeypatch.setenv("MYSQL_HOST", "env-db-host")
        monkeypatch.setenv("THRESHOLD_AUTO_MERGE", "0.95")

        cfg = load_config(str(config_file))
        assert cfg.server.port == 9999
        assert cfg.mysql.host == "env-db-host"
        assert cfg.thresholds.auto_merge == 0.95

    def test_mcp_config_path_env(self, tmp_path, monkeypatch):
        self._clear_env(monkeypatch)
        config_data = {"server": {"port": 7777}}
        config_file = tmp_path / "custom.yaml"
        config_file.write_text(yaml.dump(config_data))

        monkeypatch.setenv("MCP_CONFIG_PATH", str(config_file))
        cfg = load_config()  # no path arg
        assert cfg.server.port == 7777

    def test_missing_yaml_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_all_sections_loaded(self, tmp_path, monkeypatch):
        self._clear_env(monkeypatch)
        config_data = {
            "server": {"host": "h", "port": 1},
            "thresholds": {"auto_merge": 0.5},
            "weights": {"identity": 0.1},
            "re_evaluation": {"max_chain_depth": 5},
            "llm": {"provider": "test"},
            "embedding": {"provider": "test"},
            "neo4j": {"uri": "bolt://neo4j-host:7687", "password": "test_pass"},
            "redis": {"host": "redis-host", "port": 6380},
            "mysql": {"host": "m"},
            "buckets": {"max_commodity_keywords": 10},
        }
        config_file = tmp_path / "full.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = load_config(str(config_file))
        assert cfg.server.host == "h"
        assert cfg.re_evaluation.max_chain_depth == 5
        assert cfg.llm.provider == "test"
        assert cfg.embedding.provider == "test"
        assert cfg.neo4j.uri == "bolt://neo4j-host:7687"
        assert cfg.neo4j.password == "test_pass"
        assert cfg.redis.host == "redis-host"
        assert cfg.redis.port == 6380
