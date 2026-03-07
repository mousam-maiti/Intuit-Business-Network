"""
Tests for config.py — _env(), _build(), load_config().
"""
import os
import pytest
import tempfile
import yaml

from config import (
    _env, _build, load_config, AgentConfig,
    Thresholds, Weights, MySQLConfig, TelemetryConfig,
)


# ══════════════════════════════════════════════════════════════
# TestEnvHelper
# ══════════════════════════════════════════════════════════════

class TestEnvHelper:
    def test_returns_default_when_unset(self):
        assert _env("NONEXISTENT_VAR_12345", "fallback") == "fallback"

    def test_returns_env_value_when_set(self, monkeypatch):
        monkeypatch.setenv("TEST_ENV_VAR", "hello")
        assert _env("TEST_ENV_VAR", "default") == "hello"

    def test_casts_float(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "0.95")
        result = _env("TEST_FLOAT", 0.5, cast=float)
        assert result == 0.95
        assert isinstance(result, float)

    def test_casts_int(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "42")
        result = _env("TEST_INT", 10, cast=int)
        assert result == 42
        assert isinstance(result, int)

    def test_casts_bool_true(self, monkeypatch):
        for val in ("true", "1", "yes", "True", "YES"):
            monkeypatch.setenv("TEST_BOOL", val)
            assert _env("TEST_BOOL", False, cast=bool) is True

    def test_casts_bool_false(self, monkeypatch):
        for val in ("false", "0", "no"):
            monkeypatch.setenv("TEST_BOOL", val)
            assert _env("TEST_BOOL", True, cast=bool) is False


# ══════════════════════════════════════════════════════════════
# TestBuildHelper
# ══════════════════════════════════════════════════════════════

class TestBuildHelper:
    def test_build_from_dict(self):
        result = _build(Thresholds, {"auto_merge": 0.9, "human_review": 0.7})
        assert result.auto_merge == 0.9
        assert result.human_review == 0.7
        assert result.new_entity == 0.60  # default

    def test_ignores_unknown_keys(self):
        result = _build(Thresholds, {"auto_merge": 0.9, "unknown_key": "ignored"})
        assert result.auto_merge == 0.9
        assert not hasattr(result, "unknown_key")

    def test_none_returns_defaults(self):
        result = _build(Thresholds, None)
        assert result.auto_merge == 0.85
        assert result.human_review == 0.60


# ══════════════════════════════════════════════════════════════
# TestLoadConfig
# ══════════════════════════════════════════════════════════════

class TestLoadConfig:
    def test_loads_from_yaml(self):
        config_path = os.path.join(os.path.dirname(__file__), "..", "agent-config.yaml")
        if not os.path.exists(config_path):
            pytest.skip("agent-config.yaml not found")
        cfg = load_config(config_path)
        assert isinstance(cfg, AgentConfig)
        assert isinstance(cfg.thresholds, Thresholds)

    def test_yaml_threshold_values(self):
        config_path = os.path.join(os.path.dirname(__file__), "..", "agent-config.yaml")
        if not os.path.exists(config_path):
            pytest.skip("agent-config.yaml not found")
        cfg = load_config(config_path)
        assert cfg.thresholds.auto_merge == 0.85
        assert cfg.thresholds.human_review == 0.60

    def test_env_overrides_threshold(self, monkeypatch):
        monkeypatch.setenv("THRESHOLD_AUTO_MERGE", "0.90")
        config_path = os.path.join(os.path.dirname(__file__), "..", "agent-config.yaml")
        if not os.path.exists(config_path):
            pytest.skip("agent-config.yaml not found")
        cfg = load_config(config_path)
        assert cfg.thresholds.auto_merge == 0.90

    def test_env_overrides_mysql(self, monkeypatch):
        monkeypatch.setenv("MYSQL_HOST", "custom-host.example.com")
        monkeypatch.setenv("MYSQL_PORT", "3307")
        config_path = os.path.join(os.path.dirname(__file__), "..", "agent-config.yaml")
        if not os.path.exists(config_path):
            pytest.skip("agent-config.yaml not found")
        cfg = load_config(config_path)
        assert cfg.mysql.host == "custom-host.example.com"
        assert cfg.mysql.port == 3307

    def test_env_overrides_otel(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        config_path = os.path.join(os.path.dirname(__file__), "..", "agent-config.yaml")
        if not os.path.exists(config_path):
            pytest.skip("agent-config.yaml not found")
        cfg = load_config(config_path)
        assert cfg.telemetry.enabled is False

    def test_weights_sum_to_one(self):
        config_path = os.path.join(os.path.dirname(__file__), "..", "agent-config.yaml")
        if not os.path.exists(config_path):
            pytest.skip("agent-config.yaml not found")
        cfg = load_config(config_path)
        w = cfg.weights
        total = w.identity + w.industry + w.location + w.commodity + w.behavioral
        assert abs(total - 1.0) < 0.001

    def test_missing_yaml_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_custom_path_via_env(self, monkeypatch, tmp_path):
        cfg_file = tmp_path / "custom.yaml"
        cfg_file.write_text(yaml.dump({
            "thresholds": {"auto_merge": 0.75},
        }))
        monkeypatch.setenv("AGENT_CONFIG_PATH", str(cfg_file))
        # Clear any threshold override env vars
        monkeypatch.delenv("THRESHOLD_AUTO_MERGE", raising=False)
        cfg = load_config()
        assert cfg.thresholds.auto_merge == 0.75

    def test_empty_yaml_returns_defaults(self, tmp_path):
        cfg_file = tmp_path / "empty.yaml"
        cfg_file.write_text("")
        cfg = load_config(str(cfg_file))
        assert isinstance(cfg, AgentConfig)
        assert cfg.thresholds.auto_merge == 0.85
