"""
Tests for main.py — FastAPI endpoint tests.

Uses monkeypatch to inject mock_orchestrator into main module globals.
"""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# ══════════════════════════════════════════════════════════════
# Setup: Build a test client with mocked orchestrator
# ══════════════════════════════════════════════════════════════

@pytest.fixture
def test_client(mock_orchestrator):
    """Build FastAPI TestClient with injected mock orchestrator."""
    import main
    # Inject mock orchestrator
    main.orchestrator = mock_orchestrator
    main.stats = {"requests": 0, "merges": 0, "creates": 0, "reviews": 0, "errors": 0, "start_time": time.time()}

    # Use TestClient without lifespan to avoid connecting real clients
    with TestClient(main.app, raise_server_exceptions=False) as client:
        yield client

    # Cleanup
    main.orchestrator = None


# ══════════════════════════════════════════════════════════════
# TestHealth
# ══════════════════════════════════════════════════════════════

class TestHealth:
    def test_returns_200(self, test_client):
        resp = test_client.get("/health")
        assert resp.status_code == 200

    def test_response_format(self, test_client):
        resp = test_client.get("/health")
        data = resp.json()
        assert data["status"] == "healthy"
        assert "service" in data
        assert "version" in data


# ══════════════════════════════════════════════════════════════
# TestStats
# ══════════════════════════════════════════════════════════════

class TestStats:
    def test_returns_200(self, test_client):
        resp = test_client.get("/stats")
        assert resp.status_code == 200

    def test_includes_uptime(self, test_client):
        resp = test_client.get("/stats")
        data = resp.json()
        assert "uptime_seconds" in data

    def test_initial_values(self, test_client):
        resp = test_client.get("/stats")
        data = resp.json()
        assert data["requests"] == 0
        assert data["merges"] == 0
        assert data["errors"] == 0


# ══════════════════════════════════════════════════════════════
# TestResolve
# ══════════════════════════════════════════════════════════════

class TestResolve:
    def _valid_body(self):
        return {
            "event_id": "E-api-test",
            "record_id": "R-api-test",
            "classified_persona": {
                "identity": {"normalized_name": "API TEST ENTITY"},
                "location": {"state": "TX"},
            },
        }

    def test_returns_200(self, test_client):
        resp = test_client.post("/resolve", json=self._valid_body())
        assert resp.status_code == 200

    def test_increments_requests(self, test_client):
        import main
        before = main.stats["requests"]
        test_client.post("/resolve", json=self._valid_body())
        assert main.stats["requests"] == before + 1

    def test_increments_creates_on_new_entity(self, test_client):
        import main
        test_client.post("/resolve", json=self._valid_body())
        # No candidates = NEW_ENTITY = increments creates
        assert main.stats["creates"] >= 1

    def test_response_has_decision(self, test_client):
        resp = test_client.post("/resolve", json=self._valid_body())
        data = resp.json()
        assert "decision" in data
        assert data["decision"] in ("MERGE", "NEW_ENTITY", "REVIEW", "NO_MERGE_FOUND")

    def test_response_has_event_id(self, test_client):
        resp = test_client.post("/resolve", json=self._valid_body())
        data = resp.json()
        assert data["event_id"] == "E-api-test"

    def test_response_has_evaluation_chain(self, test_client):
        resp = test_client.post("/resolve", json=self._valid_body())
        data = resp.json()
        assert "evaluation_chain" in data
        assert isinstance(data["evaluation_chain"], list)

    def test_422_on_missing_event_id(self, test_client):
        resp = test_client.post("/resolve", json={
            "record_id": "R-1",
            "classified_persona": {},
        })
        assert resp.status_code == 422

    def test_422_on_invalid_body(self, test_client):
        resp = test_client.post("/resolve", json={"invalid": "data"})
        assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════
# TestReEvaluate
# ══════════════════════════════════════════════════════════════

class TestReEvaluate:
    def _valid_body(self):
        return {
            "golden_record_id": "G-reeval-api",
            "new_bucket_keys": ["name:TEST+TX"],
        }

    def test_returns_200(self, test_client):
        resp = test_client.post("/re-evaluate", json=self._valid_body())
        assert resp.status_code == 200

    def test_increments_requests(self, test_client):
        import main
        before = main.stats["requests"]
        test_client.post("/re-evaluate", json=self._valid_body())
        assert main.stats["requests"] == before + 1

    def test_422_on_invalid_body(self, test_client):
        resp = test_client.post("/re-evaluate", json={"invalid": True})
        assert resp.status_code == 422
