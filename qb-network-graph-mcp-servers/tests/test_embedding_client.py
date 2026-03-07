"""Tests for clients/embedding_client.py — mock mode embedding + similarity."""
import pytest
import numpy as np
from config import EmbeddingConfig
from clients.embedding_client import EmbeddingClient, _cosine


@pytest.fixture
def client():
    c = EmbeddingClient(EmbeddingConfig())
    c._using_mock = True
    return c


class TestCosine:
    def test_identical_vectors(self):
        a = np.array([1.0, 0.0, 0.0])
        assert _cosine(a, a) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert _cosine(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        assert _cosine(a, b) == pytest.approx(-1.0)

    def test_none_input(self):
        a = np.array([1.0, 0.0])
        assert _cosine(None, a) == 0.0
        assert _cosine(a, None) == 0.0

    def test_zero_vector(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 0.0])
        assert _cosine(a, b) == 0.0


class TestEmbed:
    def test_mock_returns_vector(self, client):
        vec = client.embed("hello world")
        assert vec is not None
        assert len(vec) == client._dimension

    def test_mock_deterministic(self, client):
        """Same text should produce same mock vector."""
        v1 = client.embed("test")
        v2 = client.embed("test")
        np.testing.assert_array_equal(v1, v2)

    def test_mock_different_texts(self, client):
        """Different texts should produce different vectors."""
        v1 = client.embed("alpha")
        v2 = client.embed("omega")
        assert not np.array_equal(v1, v2)

    def test_mock_normalized(self, client):
        """Mock vectors should be normalized to unit length."""
        vec = client.embed("test")
        norm = np.linalg.norm(vec)
        assert norm == pytest.approx(1.0, abs=0.01)

    def test_empty_text(self, client):
        assert client.embed("") is None

    def test_none_text(self, client):
        assert client.embed(None) is None

    def test_whitespace_only(self, client):
        assert client.embed("   ") is None


class TestEmbedBatch:
    def test_multiple_texts(self, client):
        results = client.embed_batch(["hello", "world", "test"])
        assert len(results) == 3
        assert all(r is not None for r in results)

    def test_mixed_with_empty(self, client):
        results = client.embed_batch(["hello", "", "test"])
        assert results[0] is not None
        assert results[1] is None
        assert results[2] is not None

    def test_empty_list(self, client):
        assert client.embed_batch([]) == []


class TestComputeSimilarity:
    def test_identical_texts(self, client):
        texts = {"name": "Bob's Plumbing", "industry": "238220", "commodities": "pvc pipe", "location": "Austin TX"}
        weights = {"identity": 0.35, "industry": 0.25, "commodity": 0.15, "location": 0.15}
        result = client.compute_similarity(texts, texts, weights)
        assert result["composite_similarity"] >= 0.9
        assert result["model_used"] == "mock"

    def test_different_texts(self, client):
        orphan_texts = {"name": "Bob's Plumbing", "industry": "238220", "commodities": "pvc pipe", "location": "Austin TX"}
        candidate_texts = {"name": "Acme Software", "industry": "511210", "commodities": "saas", "location": "Seattle WA"}
        weights = {"identity": 0.35, "industry": 0.25, "commodity": 0.15, "location": 0.15}
        result = client.compute_similarity(orphan_texts, candidate_texts, weights)
        # Different texts should produce lower similarity
        assert "composite_similarity" in result
        assert 0.0 <= result["composite_similarity"] <= 1.0

    def test_empty_dimension_skipped(self, client):
        orphan_texts = {"name": "Bob's Plumbing", "industry": "", "commodities": "", "location": ""}
        candidate_texts = {"name": "Bob's Plumbing", "industry": "238220", "commodities": "pvc", "location": "TX"}
        weights = {"identity": 0.35, "industry": 0.25, "commodity": 0.15, "location": 0.15}
        result = client.compute_similarity(orphan_texts, candidate_texts, weights)
        # Only name dimension should have non-zero similarity
        assert result["industry_similarity"] == 0.0

    def test_all_empty(self, client):
        empty = {"name": "", "industry": "", "commodities": "", "location": ""}
        weights = {"identity": 0.35, "industry": 0.25, "commodity": 0.15, "location": 0.15}
        result = client.compute_similarity(empty, empty, weights)
        assert result["composite_similarity"] == 0.0

    def test_output_keys(self, client):
        texts = {"name": "test", "industry": "test", "commodities": "test", "location": "test"}
        weights = {"identity": 0.35, "industry": 0.25, "commodity": 0.15, "location": 0.15}
        result = client.compute_similarity(texts, texts, weights)
        assert "name_similarity" in result
        assert "industry_similarity" in result
        assert "commodity_similarity" in result
        assert "location_similarity" in result
        assert "composite_similarity" in result
        assert "model_used" in result
        assert "inference_ms" in result

    def test_similarity_clamped(self, client):
        """All similarity scores should be in [0, 1]."""
        texts = {"name": "test", "industry": "test", "commodities": "test", "location": "test"}
        weights = {"identity": 0.35, "industry": 0.25, "commodity": 0.15, "location": 0.15}
        result = client.compute_similarity(texts, texts, weights)
        for key in ["name_similarity", "industry_similarity", "commodity_similarity", "location_similarity"]:
            assert 0.0 <= result[key] <= 1.0


class TestProperties:
    def test_is_mock(self, client):
        assert client.is_mock is True
