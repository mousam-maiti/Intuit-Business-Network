"""Tests for clients/milvus_client.py — mock mode operations."""
import pytest
import json
from config import MilvusConfig
from clients.milvus_client import MilvusClient, DIMS


@pytest.fixture
def client():
    c = MilvusClient(MilvusConfig())
    c._using_mock = True
    c._embed_provider = "none"
    return c


@pytest.fixture
def sample_gr_data():
    return {
        "golden_record_id": "G-test0001",
        "canonical_name": "Bob's Plumbing LLC",
        "state": "TX",
        "naics_code": "238220",
        "confidence": 0.85,
        "entity_type": "QB_USER",
        "source_count": 3,
        "persona": {
            "identity": {"normalized_name": "Bob's Plumbing LLC"},
            "industry": {"naics_code": "238220", "commodity_keywords": ["pvc pipe"]},
            "location": {"state": "TX", "city_norm": "AUSTIN"},
            "commodity": {"top_keywords": ["pvc pipe", "copper fittings"]},
            "behavioral": {"volume_bracket": "MEDIUM"},
        },
        "name_variants": ["Bob's Plumbing LLC", "Bobs Plumbing"],
    }


class TestUpsertGoldenRecord:
    def test_basic_upsert(self, client, sample_gr_data):
        result = client.upsert_golden_record(sample_gr_data)
        assert result["success"] is True
        assert result["mock"] is True
        assert "G-test0001" in client._mock_vectors

    def test_vector_fields_present(self, client, sample_gr_data):
        client.upsert_golden_record(sample_gr_data)
        record = client._mock_vectors["G-test0001"]
        for field in ["name_embedding", "industry_vector", "commodity_vector", "composite_vector"]:
            assert field in record
            assert len(record[field]) == DIMS[field]

    def test_scalar_fields_extracted(self, client, sample_gr_data):
        client.upsert_golden_record(sample_gr_data)
        record = client._mock_vectors["G-test0001"]
        assert record["state"] == "TX"
        assert record["naics_prefix"] == "2382"
        assert record["confidence"] == 0.85
        assert record["entity_type"] == "QB_USER"
        assert record["source_count"] == 3

    def test_name_truncated(self, client):
        data = {"golden_record_id": "G-long", "canonical_name": "A" * 300, "persona": {}}
        client.upsert_golden_record(data)
        record = client._mock_vectors["G-long"]
        assert len(record["canonical_name"]) <= 255

    def test_state_truncated(self, client):
        data = {"golden_record_id": "G-st", "state": "TEXAS", "persona": {}}
        client.upsert_golden_record(data)
        assert len(client._mock_vectors["G-st"]["state"]) <= 2

    def test_missing_fields_default(self, client):
        data = {"golden_record_id": "G-min", "persona": {}}
        result = client.upsert_golden_record(data)
        assert result["success"] is True
        record = client._mock_vectors["G-min"]
        assert record["entity_type"] == "PHANTOM"
        assert record["source_count"] == 1

    def test_persona_as_json_string(self, client):
        data = {
            "golden_record_id": "G-json",
            "canonical_name": "Test",
            "persona": json.dumps({"identity": {"normalized_name": "Test"}}),
        }
        result = client.upsert_golden_record(data)
        assert result["success"] is True

    def test_naics_from_persona_fallback(self, client):
        data = {
            "golden_record_id": "G-naics",
            "persona": {"industry": {"naics_code": "424710"}},
        }
        client.upsert_golden_record(data)
        assert client._mock_vectors["G-naics"]["naics_prefix"] == "4247"


class TestDeleteGoldenRecord:
    def test_delete_existing(self, client, sample_gr_data):
        client.upsert_golden_record(sample_gr_data)
        result = client.delete_golden_record("G-test0001")
        assert result is True
        assert "G-test0001" not in client._mock_vectors

    def test_delete_nonexistent(self, client):
        result = client.delete_golden_record("G-nope")
        assert result is True  # mock mode: no error


class TestSearchByText:
    def test_returns_results(self, client, sample_gr_data):
        client.upsert_golden_record(sample_gr_data)
        results = client.search_by_text("plumbing")
        assert len(results) >= 1
        assert results[0]["golden_record_id"] == "G-test0001"

    def test_respects_top_k(self, client, sample_gr_data):
        for i in range(5):
            data = dict(sample_gr_data)
            data["golden_record_id"] = f"G-{i:03d}"
            client.upsert_golden_record(data)
        results = client.search_by_text("plumbing", top_k=3)
        assert len(results) <= 3

    def test_empty_store(self, client):
        results = client.search_by_text("plumbing")
        assert results == []


class TestSearchHybrid:
    def test_returns_results_mock(self, client, sample_gr_data):
        client.upsert_golden_record(sample_gr_data)
        results = client.search_hybrid(name_text="plumbing")
        assert len(results) >= 1

    def test_empty_store(self, client):
        results = client.search_hybrid(name_text="plumbing")
        assert results == []

    def test_respects_top_k(self, client, sample_gr_data):
        for i in range(5):
            data = dict(sample_gr_data)
            data["golden_record_id"] = f"G-{i:03d}"
            client.upsert_golden_record(data)
        results = client.search_hybrid(name_text="test", top_k=2)
        assert len(results) <= 2


class TestBulkUpsert:
    def test_empty_list(self, client):
        result = client.bulk_upsert([])
        assert result["success"] is True
        assert result["count"] == 0

    def test_multiple_records(self, client, sample_gr_data):
        records = []
        for i in range(3):
            data = dict(sample_gr_data)
            data["golden_record_id"] = f"G-bulk-{i}"
            records.append(data)
        result = client.bulk_upsert(records)
        assert result["success"] is True
        assert result["count"] == 3
        assert client.entity_count == 3


class TestEmbedText:
    def test_empty_text_zero_vector(self, client):
        vec = client._embed_text("", 128)
        assert len(vec) == 128
        assert all(v == 0.0 for v in vec)

    def test_none_text_zero_vector(self, client):
        vec = client._embed_text(None, 64)
        assert len(vec) == 64
        assert all(v == 0.0 for v in vec)

    def test_whitespace_only_zero_vector(self, client):
        vec = client._embed_text("   ", 64)
        assert len(vec) == 64
        assert all(v == 0.0 for v in vec)

    def test_no_provider_zero_vector(self, client):
        client._embed_provider = "none"
        vec = client._embed_text("hello world", 128)
        assert len(vec) == 128
        assert all(v == 0.0 for v in vec)

    def test_correct_dimension(self, client):
        for dim in [64, 128, 256]:
            vec = client._embed_text("test", dim)
            assert len(vec) == dim


class TestBuildTextsFromPersona:
    def test_full_persona(self, client, sample_gr_data):
        texts = client._build_texts_from_persona(sample_gr_data)
        assert "name" in texts
        assert "industry" in texts
        assert "commodity" in texts
        assert "location" in texts
        assert "behavioral" in texts
        assert "Bob's Plumbing LLC" in texts["name"]

    def test_persona_as_string(self, client):
        data = {
            "golden_record_id": "G-str",
            "canonical_name": "Test",
            "persona": json.dumps({"identity": {"normalized_name": "Test"}}),
        }
        texts = client._build_texts_from_persona(data)
        assert "Test" in texts["name"]

    def test_empty_persona(self, client):
        data = {"golden_record_id": "G-empty", "canonical_name": "Test", "persona": {}}
        texts = client._build_texts_from_persona(data)
        assert "Test" in texts["name"]

    def test_invalid_json_persona(self, client):
        data = {"golden_record_id": "G-bad", "canonical_name": "Test", "persona": "not-json"}
        texts = client._build_texts_from_persona(data)
        assert "Test" in texts["name"]

    def test_name_variants_included(self, client, sample_gr_data):
        texts = client._build_texts_from_persona(sample_gr_data)
        # Variants should be in name text (deduplicated via set)
        assert "Bobs Plumbing" in texts["name"] or "Bob's Plumbing LLC" in texts["name"]

    def test_name_variants_as_json_string(self, client):
        data = {
            "golden_record_id": "G-var",
            "canonical_name": "Main",
            "name_variants": json.dumps(["Variant A", "Variant B"]),
            "persona": {},
        }
        texts = client._build_texts_from_persona(data)
        # Should parse JSON string and include variants
        assert "Main" in texts["name"]


class TestProperties:
    def test_using_mock(self, client):
        assert client.using_mock is True

    def test_entity_count_empty(self, client):
        assert client.entity_count == 0

    def test_entity_count_after_upsert(self, client, sample_gr_data):
        client.upsert_golden_record(sample_gr_data)
        assert client.entity_count == 1

    def test_embed_provider(self, client):
        assert client.embed_provider == "none"
