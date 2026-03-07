"""Tests for clients/mysql_client.py — source data reads + pending resolution."""
import pytest
from config import MySQLConfig
from clients.mysql_client import MySQLClient
from models.audit import PendingResolution


@pytest.fixture
def client():
    c = MySQLClient(MySQLConfig())
    c._using_mock = True
    return c


class TestWritePendingResolution:
    def test_write_pending(self, client):
        pending = PendingResolution(
            match_id="PR-001",
            orphan_golden_id="G-orphan",
            candidate_golden_id="G-candidate",
            confidence=0.72,
        )
        result = client.write_pending_resolution(pending)
        assert result == "PR-001"
        assert len(client._mock_pending) == 1


class TestProperties:
    def test_using_mock(self, client):
        assert client.using_mock is True

    def test_get_company_none_in_mock(self, client):
        assert client.get_company("1") is None

    def test_get_all_companies_empty_in_mock(self, client):
        assert client.get_all_companies() == []
