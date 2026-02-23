"""Tests for clients/mysql_client.py — mock mode operations."""
import pytest
import json
from config import MySQLConfig
from clients.mysql_client import MySQLClient
from models.persona import GoldenRecord, ClassifiedPersona, IdentityDimension, IndustryDimension, LocationDimension, CommodityDimension, BehavioralDimension
from models.audit import AuditRecord, PendingResolution
from utils.bucket_keys import generate_bucket_keys


@pytest.fixture
def client():
    c = MySQLClient(MySQLConfig())
    c._using_mock = True
    return c


@pytest.fixture
def sample_gr():
    persona = ClassifiedPersona(
        identity=IdentityDimension(
            normalized_name="Bob's Plumbing LLC",
            name_first_token="BOBS",
            ein_clean="743218976",
            phone_digits="5124551234",
            email="bob@bobsplumbing.com",
            email_domain="bobsplumbing.com",
        ),
        industry=IndustryDimension(naics_code="238220", naics_sector="23", naics_subsector="238"),
        location=LocationDimension(state="TX", city_norm="AUSTIN", zip3="787", zip5="78704"),
        commodity=CommodityDimension(top_keywords=["pvc pipe", "copper fittings"]),
        behavioral=BehavioralDimension(volume_bracket="MEDIUM", avg_transaction=250.0, transaction_count=45),
    )
    return GoldenRecord(
        golden_record_id="G-test0001",
        canonical_name="Bob's Plumbing LLC",
        name_variants=["Bob's Plumbing LLC", "Bobs Plumbing"],
        persona=persona,
        source_count=3,
        confidence=0.85,
        status="ACTIVE",
        entity_type="QB_USER",
        source_records=["R-001", "R-002", "R-003"],
        bucket_keys=generate_bucket_keys(persona),
    )


class TestMockCRUD:
    def test_write_and_get(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        result = client.get_golden_record("G-test0001")
        assert result is not None
        assert result["canonical_name"] == "Bob's Plumbing LLC"
        assert result["state"] == "TX"

    def test_get_nonexistent(self, client):
        assert client.get_golden_record("G-NOPE") is None

    def test_write_dict_coercion(self, client, sample_gr):
        """Writing a dict should auto-coerce to GoldenRecord."""
        d = sample_gr.model_dump()
        d["golden_record_id"] = "G-dict-001"
        client.write_golden_record(d)
        result = client.get_golden_record("G-dict-001")
        assert result is not None

    def test_get_all_active_only(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        # Write a merged record
        merged = GoldenRecord(
            golden_record_id="G-merged",
            canonical_name="Merged Corp",
            status="MERGED",
            merged_into="G-test0001",
        )
        client.write_golden_record(merged)
        client._mock_golden["G-merged"]["status"] = "MERGED"

        active = client.get_all_golden_records(active_only=True)
        merged_list = client.get_all_golden_records(active_only=False)
        assert len(active) == 1
        assert len(merged_list) == 2

    def test_record_count(self, client, sample_gr):
        assert client.record_count == 0
        client.write_golden_record(sample_gr)
        assert client.record_count == 1


class TestBucketKeyLookup:
    def test_find_by_bucket_key(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        results = client.find_by_bucket_key("name:BOBS+TX")
        assert "G-test0001" in results

    def test_find_by_ein(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        results = client.find_by_bucket_key("ein:743218976")
        assert "G-test0001" in results

    def test_find_nonexistent_bucket(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        results = client.find_by_bucket_key("ein:000000000")
        assert results == []

    def test_malformed_bucket_key(self, client):
        results = client.find_by_bucket_key("no_colon_here")
        assert results == []

    def test_merged_excluded(self, client, sample_gr):
        """MERGED records should be excluded from bucket lookups."""
        client.write_golden_record(sample_gr)
        client._mock_golden["G-test0001"]["status"] = "MERGED"
        results = client.find_by_bucket_key("name:BOBS+TX")
        assert "G-test0001" not in results

    def test_json_string_bucket_keys(self, client):
        """bucket_keys stored as JSON string should still be searched."""
        client._mock_golden["G-json"] = {
            "status": "ACTIVE",
            "bucket_keys": json.dumps(["ein:111222333"]),
        }
        results = client.find_by_bucket_key("ein:111222333")
        assert "G-json" in results


class TestTransactionalMerge:
    def test_merge_success(self, client, sample_gr):
        # Create two records
        client.write_golden_record(sample_gr)
        absorbed = GoldenRecord(
            golden_record_id="G-absorbed",
            canonical_name="Bobs Plumbing",
            source_count=1,
        )
        client.write_golden_record(absorbed)

        audit = AuditRecord(
            audit_id="A-test", event_id="E-1", record_id="G-absorbed",
            decision="MERGE", target_golden_id="G-test0001",
        )

        result = client.transactional_merge(sample_gr, "G-absorbed", audit)
        assert result is True

        # Absorbed should be MERGED
        absorbed_data = client.get_golden_record("G-absorbed")
        assert absorbed_data["status"] == "MERGED"
        assert absorbed_data["merged_into"] == "G-test0001"

        # Audit should be recorded
        assert len(client._mock_audit) == 1

    def test_merge_nonexistent_absorbed(self, client, sample_gr):
        """Merge with nonexistent absorbed should still succeed in mock."""
        client.write_golden_record(sample_gr)
        audit = AuditRecord(
            audit_id="A-test", event_id="E-1", record_id="G-nope",
            decision="MERGE",
        )
        result = client.transactional_merge(sample_gr, "G-nope", audit)
        assert result is True  # mock mode doesn't enforce FK


class TestMarkMerged:
    def test_mark_merged(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        result = client.mark_merged("G-test0001", "G-survivor")
        assert result is True
        data = client.get_golden_record("G-test0001")
        assert data["status"] == "MERGED"
        assert data["merged_into"] == "G-survivor"

    def test_mark_merged_nonexistent(self, client):
        """Marking nonexistent record should succeed silently."""
        result = client.mark_merged("G-nope", "G-survivor")
        assert result is True


class TestWriteAudit:
    def test_write_and_retrieve(self, client):
        audit = AuditRecord(
            audit_id="A-001", event_id="E-1", record_id="R-1",
            decision="MERGE", target_golden_id="G-001", confidence=0.92,
        )
        result = client.write_audit(audit)
        assert result == "A-001"
        assert len(client._mock_audit) == 1

    def test_multiple_audits(self, client):
        for i in range(3):
            audit = AuditRecord(
                audit_id=f"A-{i:03d}", event_id=f"E-{i}", record_id=f"R-{i}",
                decision="MERGE",
            )
            client.write_audit(audit)
        assert len(client._mock_audit) == 3


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


class TestWriteGoldenRecordAndPending:
    def test_atomic_write(self, client, sample_gr):
        pending = PendingResolution(
            match_id="PR-001",
            orphan_golden_id=sample_gr.golden_record_id,
            candidate_golden_id="G-candidate",
        )
        result = client.write_golden_record_and_pending(sample_gr, pending)
        assert result == "PR-001"
        assert client.get_golden_record(sample_gr.golden_record_id) is not None
        assert len(client._mock_pending) == 1


class TestWriteRelationship:
    def test_write_relationship(self, client):
        client.write_relationship("E-001", "G-source", "G-target", volume=5000.0, count=10)
        assert "E-001" in client._mock_relationships
        rel = client._mock_relationships["E-001"]
        assert rel["source_entity_id"] == "G-source"
        assert rel["target_entity_id"] == "G-target"


class TestAggregateGoldenRecords:
    def test_aggregate_by_state(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        results = client.aggregate_golden_records("state")
        assert len(results) >= 1
        states = {r["group_value"] for r in results}
        assert "TX" in states

    def test_aggregate_by_confidence_range(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        results = client.aggregate_golden_records("confidence_range")
        assert len(results) >= 1
        ranges = {r["group_value"] for r in results}
        assert "high (>=0.85)" in ranges

    def test_aggregate_with_state_filter(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        # Should match TX
        results = client.aggregate_golden_records("state", state_filter="TX")
        assert len(results) >= 1

        # Should NOT match CA
        results = client.aggregate_golden_records("state", state_filter="CA")
        assert len(results) == 0

    def test_aggregate_with_min_confidence(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        # Confidence is 0.85, so min_confidence=0.90 should exclude
        results = client.aggregate_golden_records("state", min_confidence=0.90)
        assert len(results) == 0

    def test_aggregate_excludes_merged(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        client._mock_golden["G-test0001"]["status"] = "MERGED"
        results = client.aggregate_golden_records("state")
        assert len(results) == 0

    def test_aggregate_unknown_column(self, client):
        """Unknown group_by in mock should return empty (no SQL validation)."""
        results = client.aggregate_golden_records("unknown_column")
        assert results == []

    def test_aggregate_by_entity_type(self, client, sample_gr):
        client.write_golden_record(sample_gr)
        results = client.aggregate_golden_records("entity_type")
        types = {r["group_value"] for r in results}
        assert "QB_USER" in types

    def test_confidence_range_medium(self, client):
        """Test medium confidence range (0.60-0.85)."""
        gr = GoldenRecord(golden_record_id="G-med", canonical_name="Med", confidence=0.70, status="ACTIVE")
        client.write_golden_record(gr)
        results = client.aggregate_golden_records("confidence_range")
        ranges = {r["group_value"] for r in results}
        assert "medium (0.60-0.85)" in ranges

    def test_confidence_range_low(self, client):
        """Test low confidence range (<0.60)."""
        gr = GoldenRecord(golden_record_id="G-low", canonical_name="Low", confidence=0.30, status="ACTIVE")
        client.write_golden_record(gr)
        results = client.aggregate_golden_records("confidence_range")
        ranges = {r["group_value"] for r in results}
        assert "low (<0.60)" in ranges


class TestGetAuditTrail:
    def test_empty_trail(self, client):
        results = client.get_audit_trail("G-nope")
        assert results == []

    def test_finds_by_target_golden_id(self, client):
        audit = AuditRecord(
            audit_id="A-001", event_id="E-1", record_id="R-1",
            decision="MERGE", target_golden_id="G-target",
        )
        client.write_audit(audit)
        results = client.get_audit_trail("G-target")
        assert len(results) == 1

    def test_finds_by_record_id(self, client):
        audit = AuditRecord(
            audit_id="A-001", event_id="E-1", record_id="R-search",
            decision="MERGE",
        )
        client.write_audit(audit)
        results = client.get_audit_trail("R-search")
        assert len(results) == 1

    def test_finds_by_absorbed_golden_id(self, client):
        audit = AuditRecord(
            audit_id="A-001", event_id="E-1", record_id="R-1",
            decision="MERGE", absorbed_golden_id="G-absorbed",
        )
        client.write_audit(audit)
        results = client.get_audit_trail("G-absorbed")
        assert len(results) == 1

    def test_limit_applied(self, client):
        for i in range(5):
            audit = AuditRecord(
                audit_id=f"A-{i:03d}", event_id=f"E-{i}", record_id="R-same",
                decision="MERGE", target_golden_id="G-same",
            )
            client.write_audit(audit)
        results = client.get_audit_trail("G-same", limit=3)
        assert len(results) == 3

    def test_sorted_by_created_at(self, client):
        a1 = AuditRecord(
            audit_id="A-001", event_id="E-1", record_id="R-1",
            decision="MERGE", target_golden_id="G-target",
            created_at="2024-01-01T00:00:00",
        )
        a2 = AuditRecord(
            audit_id="A-002", event_id="E-2", record_id="R-2",
            decision="MERGE", target_golden_id="G-target",
            created_at="2024-06-01T00:00:00",
        )
        client.write_audit(a1)
        client.write_audit(a2)
        results = client.get_audit_trail("G-target")
        assert results[0]["audit_id"] == "A-002"  # newer first


class TestGenerateId:
    def test_format(self, client):
        id_val = client.generate_id("G")
        assert id_val.startswith("G-")
        assert len(id_val) == 10  # "G-" + 8 hex chars

    def test_uniqueness(self, client):
        ids = {client.generate_id("G") for _ in range(100)}
        assert len(ids) == 100  # all unique

    def test_prefix(self, client):
        assert client.generate_id("A").startswith("A-")
        assert client.generate_id("PR").startswith("PR-")


class TestProperties:
    def test_using_mock(self, client):
        assert client.using_mock is True

    def test_record_count_empty(self, client):
        assert client.record_count == 0
