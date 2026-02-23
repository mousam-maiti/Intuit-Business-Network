"""
Tests for clients/milvus_client.py — mock mode, vector computation.
"""
import pytest
from config import MilvusConfig
from clients.milvus_client import MilvusClient


@pytest.fixture
def client():
    c = MilvusClient(MilvusConfig())
    c._using_mock = True
    c._embed_provider = "none"
    return c


@pytest.fixture
def sample_gr_data():
    return {
        "golden_record_id": "G-milvus01",
        "canonical_name": "BOBS PLUMBING",
        "name_variants": ["BOBS PLUMBING", "BP LLC"],
        "persona": {
            "identity": {"normalized_name": "BOBS PLUMBING"},
            "industry": {"naics_code": "238220", "original_category": "Plumbing"},
            "location": {"state": "TX", "city_norm": "AUSTIN", "zip5": "78701"},
            "commodity": {"top_keywords": ["pvc pipe", "copper fittings"]},
            "behavioral": {"volume_bracket": "MEDIUM"},
        },
        "state": "TX",
        "confidence": 0.75,
        "entity_type": "PHANTOM",
        "source_count": 2,
    }


# ══════════════════════════════════════════════════════════════
# TestMockMode
# ══════════════════════════════════════════════════════════════

class TestMockMode:
    def test_uses_mock(self, client):
        assert client._using_mock is True

    def test_using_mock_property(self, client):
        assert client.using_mock is True

    def test_entity_count_starts_zero(self, client):
        assert client.entity_count == 0

    def test_embed_provider(self, client):
        assert client.embed_provider == "none"


# ══════════════════════════════════════════════════════════════
# TestUpsert
# ══════════════════════════════════════════════════════════════

class TestUpsert:
    def test_upsert_stores_in_mock(self, client, sample_gr_data):
        result = client.upsert_golden_record(sample_gr_data)
        assert result["success"] is True
        assert result["mock"] is True
        assert "G-milvus01" in client._mock_vectors

    def test_returns_success(self, client, sample_gr_data):
        result = client.upsert_golden_record(sample_gr_data)
        assert result["success"] is True

    def test_overwrites_existing(self, client, sample_gr_data):
        client.upsert_golden_record(sample_gr_data)
        sample_gr_data["canonical_name"] = "UPDATED NAME"
        client.upsert_golden_record(sample_gr_data)
        assert client._mock_vectors["G-milvus01"]["canonical_name"] == "UPDATED NAME"

    def test_entity_count_increments(self, client, sample_gr_data):
        client.upsert_golden_record(sample_gr_data)
        assert client.entity_count == 1

    def test_upsert_has_exactly_4_vector_fields(self, client, sample_gr_data):
        """Only 4 vector fields stored — no location_embedding or behavioral_vector."""
        client.upsert_golden_record(sample_gr_data)
        record = client._mock_vectors["G-milvus01"]
        expected = {"name_embedding", "industry_vector", "commodity_vector", "composite_vector"}
        actual = {k for k, v in record.items() if isinstance(v, list)}
        assert actual == expected


# ══════════════════════════════════════════════════════════════
# TestDelete
# ══════════════════════════════════════════════════════════════

class TestDelete:
    def test_delete_existing(self, client, sample_gr_data):
        client.upsert_golden_record(sample_gr_data)
        assert client.entity_count == 1
        result = client.delete_golden_record("G-milvus01")
        assert result is True
        assert client.entity_count == 0

    def test_delete_nonexistent(self, client):
        result = client.delete_golden_record("G-nonexistent")
        assert result is True  # Mock silently succeeds


# ══════════════════════════════════════════════════════════════
# TestSearch
# ══════════════════════════════════════════════════════════════

class TestSearch:
    def test_search_by_text_mock(self, client, sample_gr_data):
        client.upsert_golden_record(sample_gr_data)
        results = client.search_by_text("plumbing", top_k=5)
        assert len(results) >= 1

    def test_search_empty_mock(self, client):
        results = client.search_by_text("anything", top_k=5)
        assert results == []

    def test_search_hybrid_mock(self, client, sample_gr_data):
        client.upsert_golden_record(sample_gr_data)
        results = client.search_hybrid(
            name_text="bobs", industry_text="plumbing", top_k=5,
        )
        assert len(results) >= 1


# ══════════════════════════════════════════════════════════════
# TestBulkUpsert
# ══════════════════════════════════════════════════════════════

class TestBulkUpsert:
    def test_empty_list(self, client):
        result = client.bulk_upsert([])
        assert result["success"] is True
        assert result["count"] == 0

    def test_multiple_records(self, client, sample_gr_data):
        records = [
            {**sample_gr_data, "golden_record_id": f"G-bulk{i}"}
            for i in range(5)
        ]
        result = client.bulk_upsert(records)
        assert result["success"] is True
        assert result["count"] == 5
        assert client.entity_count == 5


# ══════════════════════════════════════════════════════════════
# TestBuildTexts
# ══════════════════════════════════════════════════════════════

class TestBuildTexts:
    def test_name_industry_text(self, client, sample_gr_data):
        texts = client._build_texts_from_persona(sample_gr_data)
        assert "BOBS PLUMBING" in texts["name"]
        assert "Plumbing" in texts["industry"]

    def test_location_and_behavioral_text_still_generated(self, client, sample_gr_data):
        """Location + behavioral text is still produced for composite embedding."""
        texts = client._build_texts_from_persona(sample_gr_data)
        assert "AUSTIN" in texts["location"]
        assert "TX" in texts["location"]
        assert "MEDIUM" in texts["behavioral"]

    def test_json_string_persona(self, client):
        import json
        gr_data = {
            "golden_record_id": "G-json",
            "canonical_name": "JSON TEST",
            "persona": json.dumps({
                "identity": {"normalized_name": "JSON TEST"},
                "industry": {"naics_code": "111"},
            }),
        }
        texts = client._build_texts_from_persona(gr_data)
        assert "JSON TEST" in texts["name"]

    def test_empty_persona(self, client):
        gr_data = {"golden_record_id": "G-empty", "canonical_name": "EMPTY"}
        texts = client._build_texts_from_persona(gr_data)
        assert "EMPTY" in texts["name"]
