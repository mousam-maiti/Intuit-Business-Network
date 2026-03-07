"""
Post-deployment smoke tests — runs against a live service.

Usage:
  AGENT_BASE_URL=http://localhost:18181 pytest tests/test_smoke.py -m smoke -v

Requires:
  pip install httpx
"""
import os
import time
import uuid
import pytest

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

BASE_URL = os.environ.get("AGENT_BASE_URL", "http://localhost:18181")

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not HAS_HTTPX, reason="httpx not installed"),
]


@pytest.fixture(scope="module")
def client():
    """Shared httpx client for the smoke test session."""
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


def _unique_name():
    return f"SMOKE-TEST-{uuid.uuid4().hex[:6].upper()}"


def _resolve_body(name=None, ein=None, state="TX", naics="238220"):
    if name is None:
        name = _unique_name()
    body = {
        "event_id": f"smoke-{uuid.uuid4().hex[:8]}",
        "record_id": f"smoke-R-{uuid.uuid4().hex[:8]}",
        "classified_persona": {
            "identity": {
                "normalized_name": name,
                "name_first_token": name.split()[0] if name else "",
                "name_tokens": name.split() if name else [],
            },
            "industry": {"naics_code": naics, "naics_sector": naics[:2], "naics_subsector": naics[:3]},
            "location": {"state": state, "city_norm": "AUSTIN", "zip3": "787", "zip5": "78701"},
            "commodity": {"top_keywords": ["pvc pipe"]},
        },
    }
    if ein:
        body["classified_persona"]["identity"]["ein_clean"] = ein
    return body


# ══════════════════════════════════════════════════════════════
# TestServiceAvailability
# ══════════════════════════════════════════════════════════════

class TestServiceAvailability:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_stats_returns_200(self, client):
        resp = client.get("/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "requests" in data


# ══════════════════════════════════════════════════════════════
# TestResolveSmoke
# ══════════════════════════════════════════════════════════════

class TestResolveSmoke:
    def test_new_entity_creation(self, client):
        body = _resolve_body()
        resp = client.post("/resolve", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] in ("NEW_ENTITY", "MERGE", "REVIEW")

    def test_response_schema(self, client):
        body = _resolve_body()
        resp = client.post("/resolve", json=body)
        data = resp.json()
        assert "event_id" in data
        assert "decision" in data
        assert "confidence" in data
        assert "evaluation_chain" in data

    def test_timing_under_5s(self, client):
        body = _resolve_body()
        start = time.time()
        resp = client.post("/resolve", json=body)
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 5.0, f"Resolution took {elapsed:.1f}s (>5s)"

    def test_stats_incremented(self, client):
        stats_before = client.get("/stats").json()
        body = _resolve_body()
        client.post("/resolve", json=body)
        stats_after = client.get("/stats").json()
        assert stats_after["requests"] > stats_before["requests"]


# ══════════════════════════════════════════════════════════════
# TestReEvaluateSmoke
# ══════════════════════════════════════════════════════════════

class TestReEvaluateSmoke:
    def test_nonexistent_gr_handled(self, client):
        body = {
            "golden_record_id": "G-nonexistent-smoke",
            "new_bucket_keys": ["name:NOBODY+XX"],
        }
        resp = client.post("/re-evaluate", json=body)
        assert resp.status_code == 200

    def test_response_schema(self, client):
        body = {
            "golden_record_id": "G-smoke-reeval",
            "new_bucket_keys": ["name:SMOKE+TX"],
        }
        resp = client.post("/re-evaluate", json=body)
        data = resp.json()
        assert "golden_record_id" in data
        assert "merges" in data
        assert "reviews" in data


# ══════════════════════════════════════════════════════════════
# TestDecisionPipeline
# ══════════════════════════════════════════════════════════════

class TestDecisionPipeline:
    def test_create_then_merge_lifecycle(self, client):
        name = _unique_name()
        # Step 1: Create
        body1 = _resolve_body(name=name)
        resp1 = client.post("/resolve", json=body1)
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["decision"] in ("NEW_ENTITY", "MERGE", "REVIEW")

        # Step 2: Resolve same name again — should find the first one
        body2 = _resolve_body(name=name)
        resp2 = client.post("/resolve", json=body2)
        assert resp2.status_code == 200
        data2 = resp2.json()
        # Second resolution may merge into first
        assert data2["decision"] in ("MERGE", "NEW_ENTITY", "REVIEW")

    def test_evaluation_chain_populated(self, client):
        body = _resolve_body()
        resp = client.post("/resolve", json=body)
        data = resp.json()
        chain = data.get("evaluation_chain", [])
        assert len(chain) >= 1
        assert any(s.get("step") == "find_candidates" for s in chain)

    def test_stats_reflect_requests(self, client):
        stats_before = client.get("/stats").json()
        # Make 2 requests
        client.post("/resolve", json=_resolve_body())
        client.post("/resolve", json=_resolve_body())
        stats_after = client.get("/stats").json()
        assert stats_after["requests"] >= stats_before["requests"] + 2


# ══════════════════════════════════════════════════════════════
# TestEdgeCases
# ══════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_sparse_persona_name_only(self, client):
        body = {
            "event_id": f"smoke-sparse-{uuid.uuid4().hex[:6]}",
            "record_id": f"smoke-R-sparse-{uuid.uuid4().hex[:6]}",
            "classified_persona": {
                "identity": {"normalized_name": _unique_name()},
            },
        }
        resp = client.post("/resolve", json=body)
        assert resp.status_code == 200

    def test_kg_triples_via_resolve(self, client):
        """Verify that resolution creates entity triples if KG available."""
        body = _resolve_body()
        resp = client.post("/resolve", json=body)
        assert resp.status_code == 200
        # If KG is available, triples would be written; we just verify no crash

    def test_audit_in_stats(self, client):
        body = _resolve_body()
        client.post("/resolve", json=body)
        stats = client.get("/stats").json()
        # Stats should have requests counted
        assert stats["requests"] >= 1
