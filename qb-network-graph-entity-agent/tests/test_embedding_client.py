"""
Tests for clients/embedding_client.py — mock mode, _cosine.
"""
import pytest
import numpy as np
from config import EmbeddingConfig
from clients.embedding_client import EmbeddingClient, _cosine


@pytest.fixture
def client():
    c = EmbeddingClient(EmbeddingConfig())
    c._using_mock = True
    return c


# ══════════════════════════════════════════════════════════════
# TestCosine
# ══════════════════════════════════════════════════════════════

class TestCosine:
    def test_identical_vectors(self):
        v = np.array([1.0, 0.0, 0.0])
        assert _cosine(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert _cosine(a, b) == pytest.approx(0.0)

    def test_zero_vector_a(self):
        a = np.array([0.0, 0.0, 0.0])
        b = np.array([1.0, 2.0, 3.0])
        assert _cosine(a, b) == 0.0

    def test_zero_vector_b(self):
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([0.0, 0.0, 0.0])
        assert _cosine(a, b) == 0.0

    def test_none_vector(self):
        assert _cosine(None, np.array([1.0])) == 0.0
        assert _cosine(np.array([1.0]), None) == 0.0


# ══════════════════════════════════════════════════════════════
# TestMockMode
# ══════════════════════════════════════════════════════════════

class TestMockMode:
    def test_is_mock_property(self, client):
        assert client.is_mock is True

    def test_empty_text_returns_none(self, client):
        assert client.embed("") is None

    def test_whitespace_returns_none(self, client):
        assert client.embed("   ") is None

    def test_deterministic_same_text(self, client):
        v1 = client.embed("hello world")
        v2 = client.embed("hello world")
        assert v1 is not None
        assert v2 is not None
        np.testing.assert_array_equal(v1, v2)

    def test_different_texts_different_vecs(self, client):
        v1 = client.embed("hello")
        v2 = client.embed("goodbye")
        assert not np.array_equal(v1, v2)

    def test_normalized_unit_length(self, client):
        v = client.embed("test text")
        assert v is not None
        norm = np.linalg.norm(v)
        assert norm == pytest.approx(1.0, abs=0.001)


# ══════════════════════════════════════════════════════════════
# TestComputeSimilarity
# ══════════════════════════════════════════════════════════════

class TestComputeSimilarity:
    def test_same_texts_high_similarity(self, client):
        texts = {"name": "BOBS PLUMBING", "industry": "plumbing", "commodities": "pvc", "location": "TX"}
        result = client.compute_similarity(texts, texts, {"identity": 0.35, "industry": 0.25, "commodity": 0.15, "location": 0.15})
        assert result["name_similarity"] == pytest.approx(1.0, abs=0.001)
        assert result["composite_similarity"] > 0.9

    def test_empty_dimension_skipped(self, client):
        orphan = {"name": "TEST", "industry": "", "commodities": "", "location": ""}
        cand = {"name": "TEST", "industry": "plumbing", "commodities": "pvc", "location": "TX"}
        result = client.compute_similarity(orphan, cand, {"identity": 0.35, "industry": 0.25, "commodity": 0.15, "location": 0.15})
        assert result["industry_similarity"] == 0.0

    def test_model_used_mock(self, client):
        texts = {"name": "A", "industry": "B", "commodities": "C", "location": "D"}
        result = client.compute_similarity(texts, texts, {"identity": 0.35})
        assert result["model_used"] == "mock"

    def test_returns_all_dimension_keys(self, client):
        texts = {"name": "A", "industry": "B", "commodities": "C", "location": "D"}
        result = client.compute_similarity(texts, texts, {"identity": 0.35})
        assert "name_similarity" in result
        assert "industry_similarity" in result
        assert "commodity_similarity" in result
        assert "location_similarity" in result
        assert "composite_similarity" in result

    def test_weighted_composite(self, client):
        orphan = {"name": "ALPHA", "industry": "tech", "commodities": "software", "location": "CA"}
        cand = {"name": "ALPHA", "industry": "tech", "commodities": "hardware", "location": "CA"}
        weights = {"identity": 0.5, "industry": 0.2, "commodity": 0.2, "location": 0.1}
        result = client.compute_similarity(orphan, cand, weights)
        # Name same = high similarity, commodities differ = lower
        assert result["composite_similarity"] > 0.0
        assert result["inference_ms"] >= 0
