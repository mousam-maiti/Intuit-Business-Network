"""
Tests for clients/mysql_client.py — all mock-mode operations.
"""
import json
import pytest
from config import MySQLConfig
from clients.mysql_client import MySQLClient
from models.persona import GoldenRecord, ClassifiedPersona, IdentityDimension, IndustryDimension, LocationDimension, CommodityDimension
from models.audit import AuditRecord, PendingResolution


@pytest.fixture
def client():
    c = MySQLClient(MySQLConfig())
    c._using_mock = True
    return c


@pytest.fixture
def sample_gr():
    return GoldenRecord(
        golden_record_id="G-test0001",
        canonical_name="BOBS PLUMBING",
        name_variants=["BOBS PLUMBING", "BP LLC"],
        persona=ClassifiedPersona(
            identity=IdentityDimension(
                normalized_name="BOBS PLUMBING",
                ein_clean="123456789",
                phone_digits="5125551234",
            ),
            industry=IndustryDimension(naics_code="238220", naics_sector="23", naics_subsector="238"),
            location=LocationDimension(state="TX", city_norm="AUSTIN", zip3="787", zip5="78701"),
            commodity=CommodityDimension(top_keywords=["pvc pipe"]),
        ),
        source_count=2,
        confidence=0.75,
        status="ACTIVE",
        entity_type="PHANTOM",
        source_records=["orphan-1", "orphan-2"],
        bucket_keys=["name:BOBS+TX", "ein:123456789"],
    )


@pytest.fixture
def sample_audit():
    return AuditRecord(
        audit_id="A-test001",
        event_id="E-001",
        record_id="R-001",
        decision="MERGE",
        confidence=0.92,
    )


# ══════════════════════════════════════════════════════════════
# TestMockMode
# ══════════════════════════════════════════════════════════════

class TestMockMode:
    def test_using_mock_flag(self, client):
        assert client._using_mock is True

    def test_using_mock_property(self, client):
        assert client.using_mock is True

    def test_generate_id_format(self, client):
        gid = client.generate_id("G")
        assert gid.startswith("G-")
        assert len(gid) == 10  # "G-" + 8 hex chars

    def test_generate_id_uniqueness(self, client):
        ids = {client.generate_id("G") for _ in range(100)}
        assert len(ids) == 100


# ══════════════════════════════════════════════════════════════
# TestGoldenRecordCRUD
# ══════════════════════════════════════════════════════════════

class TestGoldenRecordCRUD:
    def test_write_and_read_roundtrip(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        result = client.get_golden_record("G-test0001")
        assert result is not None
        assert result["canonical_name"] == "BOBS PLUMBING"
        assert result["golden_record_id"] == "G-test0001"

    def test_nonexistent_returns_none(self, client):
        assert client.get_golden_record("G-nonexistent") is None

    def test_get_all(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        gr2 = GoldenRecord(golden_record_id="G-test0002", canonical_name="OTHER")
        client.write_golden_record(gr2)
        all_records = client.get_all_golden_records(active_only=False)
        assert len(all_records) == 2

    def test_active_only_filter(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        merged_gr = GoldenRecord(
            golden_record_id="G-merged", canonical_name="MERGED",
            status="MERGED", merged_into="G-test0001",
        )
        client.write_golden_record(merged_gr)
        active = client.get_all_golden_records(active_only=True)
        assert all(r.get("status") in ("ACTIVE", "PROVISIONAL") for r in active)

    def test_includes_provisional(self, client):
        prov = GoldenRecord(
            golden_record_id="G-prov", canonical_name="PROVISIONAL",
            status="PROVISIONAL",
        )
        client.write_golden_record(prov)
        active = client.get_all_golden_records(active_only=True)
        assert any(r["golden_record_id"] == "G-prov" for r in active)

    def test_record_count(self, client, sample_gr):
        assert client.record_count == 0
        client.write_golden_record(sample_gr)
        assert client.record_count == 1

    def test_write_from_dict(self, client):
        gr_dict = {
            "golden_record_id": "G-fromdict",
            "canonical_name": "FROM DICT",
        }
        client.write_golden_record(gr_dict)
        result = client.get_golden_record("G-fromdict")
        assert result is not None
        assert result["canonical_name"] == "FROM DICT"


# ══════════════════════════════════════════════════════════════
# TestBucketSearch
# ══════════════════════════════════════════════════════════════

class TestBucketSearch:
    def test_exact_match(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        results = client.find_by_bucket_key("name:BOBS+TX")
        assert "G-test0001" in results

    def test_no_match(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        results = client.find_by_bucket_key("name:NOBODY+CA")
        assert results == []

    def test_excludes_merged(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        client._mock_golden["G-test0001"]["status"] = "MERGED"
        results = client.find_by_bucket_key("name:BOBS+TX")
        assert "G-test0001" not in results

    def test_invalid_format(self, client):
        assert client.find_by_bucket_key("nobucketformat") == []

    def test_json_string_bucket_keys(self, client):
        gr = GoldenRecord(
            golden_record_id="G-jsonbk",
            canonical_name="JSON BK",
            bucket_keys=["ein:999888777"],
        )
        client.write_golden_record(gr)
        # Simulate JSON string bucket_keys (as stored in MySQL)
        client._mock_golden["G-jsonbk"]["bucket_keys"] = json.dumps(["ein:999888777"])
        results = client.find_by_bucket_key("ein:999888777")
        assert "G-jsonbk" in results


# ══════════════════════════════════════════════════════════════
# TestTransactionalMerge
# ══════════════════════════════════════════════════════════════

class TestTransactionalMerge:
    def test_success(self, client, sample_gr, sample_audit):
        # Write absorbed first
        absorbed = GoldenRecord(golden_record_id="G-absorbed", canonical_name="ABSORBED")
        client.write_golden_record(absorbed)
        client.write_golden_record(sample_gr)

        success = client.transactional_merge(sample_gr, "G-absorbed", sample_audit)
        assert success is True
        # Survivor updated
        assert client.get_golden_record("G-test0001") is not None
        # Absorbed marked MERGED
        absorbed_data = client.get_golden_record("G-absorbed")
        assert absorbed_data["status"] == "MERGED"
        assert absorbed_data["merged_into"] == "G-test0001"
        # Audit written
        assert len(client._mock_audit) == 1

    def test_absorbed_not_found(self, client, sample_gr, sample_audit):
        client.write_golden_record(sample_gr)
        success = client.transactional_merge(sample_gr, "G-nonexistent", sample_audit)
        assert success is True  # Mock mode doesn't fail
        assert len(client._mock_audit) == 1

    def test_audit_appended(self, client, sample_gr, sample_audit):
        absorbed = GoldenRecord(golden_record_id="G-absorbed2", canonical_name="ABS2")
        client.write_golden_record(absorbed)
        client.write_golden_record(sample_gr)
        client.transactional_merge(sample_gr, "G-absorbed2", sample_audit)
        assert len(client._mock_audit) == 1
        assert client._mock_audit[0]["audit_id"] == "A-test001"


# ══════════════════════════════════════════════════════════════
# TestStandaloneWrites
# ══════════════════════════════════════════════════════════════

class TestStandaloneWrites:
    def test_mark_merged(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        client.mark_merged("G-test0001", "G-survivor")
        data = client.get_golden_record("G-test0001")
        assert data["status"] == "MERGED"
        assert data["merged_into"] == "G-survivor"

    def test_mark_merged_nonexistent(self, client):
        result = client.mark_merged("G-nonexistent", "G-survivor")
        assert result is True  # Mock always returns True

    def test_write_audit(self, client, sample_audit):
        audit_id = client.write_audit(sample_audit)
        assert audit_id == "A-test001"
        assert len(client._mock_audit) == 1

    def test_write_pending_resolution(self, client):
        pr = PendingResolution(
            match_id="PR-001",
            orphan_golden_id="G-orphan",
            candidate_golden_id="G-cand",
            confidence=0.7,
        )
        match_id = client.write_pending_resolution(pr)
        assert match_id == "PR-001"
        assert len(client._mock_pending) == 1

    def test_write_relationship(self, client):
        client.write_relationship("E-001", "G-src", "G-tgt", volume=10000.0)
        assert "E-001" in client._mock_relationships
        assert client._mock_relationships["E-001"]["source_entity_id"] == "G-src"


# ══════════════════════════════════════════════════════════════
# TestSerialization
# ══════════════════════════════════════════════════════════════

class TestSerialization:
    def test_serialize_gr_extracts_persona_fields(self, client, sample_gr):
        data = client._serialize_gr(sample_gr, "2024-01-01T00:00:00")
        assert data["ein"] == "123456789"
        assert data["phone_digits"] == "5125551234"
        assert data["state"] == "TX"
        assert data["naics_code"] == "238220"

    def test_serialize_gr_json_columns(self, client, sample_gr):
        data = client._serialize_gr(sample_gr, "2024-01-01T00:00:00")
        # These should be JSON strings
        assert isinstance(data["name_variants"], str)
        name_variants = json.loads(data["name_variants"])
        assert "BOBS PLUMBING" in name_variants

    def test_deserialize_gr_parses_json(self, client):
        row = {
            "name_variants": '["A", "B"]',
            "commodity_keywords": '["pvc"]',
            "source_records": '["r-1"]',
            "bucket_keys": '["ein:123"]',
            "persona": '{"identity": {"normalized_name": "TEST"}}',
        }
        result = client._deserialize_gr(row)
        assert result["name_variants"] == ["A", "B"]
        assert result["persona"]["identity"]["normalized_name"] == "TEST"

    def test_deserialize_gr_handles_invalid_json(self, client):
        row = {
            "name_variants": "not-valid-json{",
            "commodity_keywords": "[]",
        }
        result = client._deserialize_gr(row)
        assert result["name_variants"] == "not-valid-json{"  # left as-is
