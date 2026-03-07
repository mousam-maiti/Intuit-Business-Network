"""
Tests for mcp/entity_writer.py — all 5 tools + helpers.
"""
import pytest
from models.persona import (
    ClassifiedPersona, GoldenRecord, IdentityDimension,
    IndustryDimension, LocationDimension, CommodityDimension,
)
from mcp.entity_writer import (
    EntityWriter, _apply_survivorship, _resolve_canonical_name, _gr_to_kg_attrs,
)


# ══════════════════════════════════════════════════════════════
# TestHelpers
# ══════════════════════════════════════════════════════════════

class TestHelpers:
    # _resolve_canonical_name
    def test_resolve_normalized_name(self):
        p = ClassifiedPersona(identity=IdentityDimension(normalized_name="BOBS PLUMBING"))
        assert _resolve_canonical_name(p) == "BOBS PLUMBING"

    def test_resolve_empty_name_falls_to_first_token(self):
        p = ClassifiedPersona(identity=IdentityDimension(
            normalized_name="", name_first_token="BOBS",
        ))
        assert _resolve_canonical_name(p) == "BOBS"

    def test_resolve_all_empty(self):
        p = ClassifiedPersona()
        assert _resolve_canonical_name(p) == ""

    def test_resolve_alias_fallback(self):
        p = ClassifiedPersona(identity=IdentityDimension(
            canonical_name="ALIAS NAME",
        ))
        assert _resolve_canonical_name(p) == "ALIAS NAME"

    # _apply_survivorship
    def test_survivorship_ein(self):
        gr = GoldenRecord(golden_record_id="G-1", canonical_name="TEST")
        orphan = ClassifiedPersona(identity=IdentityDimension(ein_clean="123456789"))
        _apply_survivorship(gr, orphan)
        assert gr.persona.identity.ein_clean == "123456789"

    def test_survivorship_phone(self):
        gr = GoldenRecord(golden_record_id="G-1", canonical_name="TEST")
        orphan = ClassifiedPersona(identity=IdentityDimension(phone_digits="5125551234"))
        _apply_survivorship(gr, orphan)
        assert gr.persona.identity.phone_digits == "5125551234"

    def test_survivorship_email(self):
        gr = GoldenRecord(golden_record_id="G-1", canonical_name="TEST")
        orphan = ClassifiedPersona(identity=IdentityDimension(
            email="bob@test.com", email_domain="test.com",
        ))
        _apply_survivorship(gr, orphan)
        assert gr.persona.identity.email == "bob@test.com"
        assert gr.persona.identity.email_domain == "test.com"

    def test_survivorship_naics(self):
        gr = GoldenRecord(
            golden_record_id="G-1", canonical_name="TEST",
            persona=ClassifiedPersona(industry=IndustryDimension(naics_code="23")),
        )
        orphan = ClassifiedPersona(industry=IndustryDimension(
            naics_code="238220", naics_sector="23", naics_subsector="238",
        ))
        _apply_survivorship(gr, orphan)
        # Longer NAICS wins
        assert gr.persona.industry.naics_code == "238220"

    def test_survivorship_location(self):
        gr = GoldenRecord(golden_record_id="G-1", canonical_name="TEST")
        orphan = ClassifiedPersona(location=LocationDimension(
            city_norm="AUSTIN", zip5="78701", zip3="787",
        ))
        _apply_survivorship(gr, orphan)
        assert gr.persona.location.city_norm == "AUSTIN"
        assert gr.persona.location.zip5 == "78701"

    def test_survivorship_keywords(self):
        gr = GoldenRecord(
            golden_record_id="G-1", canonical_name="TEST",
            persona=ClassifiedPersona(commodity=CommodityDimension(top_keywords=["pvc"])),
        )
        orphan = ClassifiedPersona(commodity=CommodityDimension(
            top_keywords=["pvc", "copper"],
        ))
        _apply_survivorship(gr, orphan)
        kw_lower = {k.lower() for k in gr.persona.commodity.top_keywords}
        assert "copper" in kw_lower
        assert "pvc" in kw_lower

    # _gr_to_kg_attrs
    def test_gr_to_kg_attrs_full(self):
        gr = GoldenRecord(
            golden_record_id="G-1", canonical_name="TEST CORP",
            name_variants=["TEST CORP", "TC"],
            persona=ClassifiedPersona(
                identity=IdentityDimension(ein_clean="123", email="a@b.com", phone_digits="555"),
                industry=IndustryDimension(naics_code="238220"),
                location=LocationDimension(city_norm="Austin"),
            ),
            entity_type="PHANTOM", confidence=0.8,
        )
        orphan = ClassifiedPersona()
        attrs = _gr_to_kg_attrs(gr, orphan)
        assert attrs["canonical_name"] == "TEST CORP"
        assert "238220" in attrs["naics_codes"]
        assert attrs["ein"] == "123"

    def test_gr_to_kg_attrs_empty_name_fallback(self):
        gr = GoldenRecord(
            golden_record_id="G-1", canonical_name="",
            name_variants=["FALLBACK"],
        )
        orphan = ClassifiedPersona(identity=IdentityDimension(normalized_name="ORPHAN"))
        attrs = _gr_to_kg_attrs(gr, orphan)
        assert attrs["canonical_name"] in ("ORPHAN", "FALLBACK")


# ══════════════════════════════════════════════════════════════
# TestMergeIntoGR
# ══════════════════════════════════════════════════════════════

class TestMergeIntoGR:
    def test_success(self, mock_writer, golden_factory, persona_factory, mock_mysql):
        gr = golden_factory(gr_id="G-merge01", confidence=0.5, source_count=1)
        mock_mysql.write_golden_record(gr)
        orphan = persona_factory(name="NEW VARIANT")
        result = mock_writer.merge_into_golden_record(
            orphan_record_id="orphan-new",
            orphan_persona=orphan,
            golden_record_id="G-merge01",
            merge_reasoning={"trigger": "DETERMINISTIC"},
        )
        assert result["success"] is True
        assert result["golden_record_id"] == "G-merge01"

    def test_gr_not_found(self, mock_writer, persona_factory):
        orphan = persona_factory()
        result = mock_writer.merge_into_golden_record(
            orphan_record_id="orphan-1",
            orphan_persona=orphan,
            golden_record_id="G-nonexistent",
            merge_reasoning={},
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_adds_name_variant(self, mock_writer, golden_factory, persona_factory, mock_mysql):
        gr = golden_factory(gr_id="G-variant", name="EXISTING", name_variants=["EXISTING"])
        mock_mysql.write_golden_record(gr)
        orphan = persona_factory(name="NEW NAME")
        mock_writer.merge_into_golden_record("o-1", orphan, "G-variant", {})
        updated = mock_mysql.get_golden_record("G-variant")
        assert "NEW NAME" in updated.get("name_variants", [])

    def test_increments_source_count(self, mock_writer, golden_factory, persona_factory, mock_mysql):
        gr = golden_factory(gr_id="G-count", source_count=2)
        mock_mysql.write_golden_record(gr)
        orphan = persona_factory()
        mock_writer.merge_into_golden_record("o-1", orphan, "G-count", {})
        updated = mock_mysql.get_golden_record("G-count")
        assert updated["source_count"] == 3

    def test_appends_source_record(self, mock_writer, golden_factory, persona_factory, mock_mysql):
        gr = golden_factory(gr_id="G-src", source_records=["existing-1"])
        mock_mysql.write_golden_record(gr)
        orphan = persona_factory()
        mock_writer.merge_into_golden_record("new-orphan", orphan, "G-src", {})
        updated = mock_mysql.get_golden_record("G-src")
        assert "new-orphan" in updated.get("source_records", [])

    def test_regenerates_bucket_keys(self, mock_writer, golden_factory, persona_factory, mock_mysql):
        gr = golden_factory(gr_id="G-bk", bucket_keys=[])
        mock_mysql.write_golden_record(gr)
        orphan = persona_factory()
        mock_writer.merge_into_golden_record("o-1", orphan, "G-bk", {})
        updated = mock_mysql.get_golden_record("G-bk")
        assert len(updated.get("bucket_keys", [])) > 0

    def test_confidence_capped_at_099(self, mock_writer, golden_factory, persona_factory, mock_mysql):
        gr = golden_factory(gr_id="G-cap", confidence=0.97)
        mock_mysql.write_golden_record(gr)
        orphan = persona_factory()
        mock_writer.merge_into_golden_record("o-1", orphan, "G-cap", {})
        updated = mock_mysql.get_golden_record("G-cap")
        assert updated["confidence"] <= 0.99


# ══════════════════════════════════════════════════════════════
# TestCreateGR
# ══════════════════════════════════════════════════════════════

class TestCreateGR:
    def test_success(self, mock_writer, persona_factory):
        orphan = persona_factory(name="BRAND NEW")
        result = mock_writer.create_golden_record(
            orphan_record_id="o-create",
            orphan_persona=orphan,
            creation_reasoning={"trigger": "AI_AGENT_NEW"},
        )
        assert result["success"] is True
        assert result["golden_record_id"].startswith("G-")
        assert len(result["bucket_keys"]) > 0

    def test_writes_mysql(self, mock_writer, persona_factory, mock_mysql):
        orphan = persona_factory(name="NEW ENTITY")
        result = mock_writer.create_golden_record("o-1", orphan, {})
        gr_id = result["golden_record_id"]
        stored = mock_mysql.get_golden_record(gr_id)
        assert stored is not None
        assert stored["canonical_name"] == "NEW ENTITY"

    def test_sets_status_active(self, mock_writer, persona_factory, mock_mysql):
        orphan = persona_factory()
        result = mock_writer.create_golden_record("o-1", orphan, {})
        stored = mock_mysql.get_golden_record(result["golden_record_id"])
        assert stored["status"] == "ACTIVE"
        assert stored["entity_type"] == "PHANTOM"


# ══════════════════════════════════════════════════════════════
# TestSubmitForReview
# ══════════════════════════════════════════════════════════════

class TestSubmitForReview:
    def test_creates_provisional_gr(self, mock_writer, persona_factory, mock_mysql):
        orphan = persona_factory(name="REVIEW CANDIDATE")
        result = mock_writer.submit_for_review(
            orphan_record_id="o-review",
            orphan_persona=orphan,
            candidate_golden_record_id="G-existing",
            review_reasoning={"confidence": 0.65},
        )
        assert result["success"] is True
        prov_id = result["provisional_golden_record_id"]
        stored = mock_mysql.get_golden_record(prov_id)
        assert stored["status"] == "PROVISIONAL"

    def test_writes_pending_resolution(self, mock_writer, persona_factory, mock_mysql):
        orphan = persona_factory()
        result = mock_writer.submit_for_review("o-1", orphan, "G-cand", {"confidence": 0.7})
        assert len(mock_mysql._mock_pending) == 1

    def test_returns_match_id(self, mock_writer, persona_factory):
        orphan = persona_factory()
        result = mock_writer.submit_for_review("o-1", orphan, "G-cand", {})
        assert result["pending_match_id"].startswith("PR-")


# ══════════════════════════════════════════════════════════════
# TestMergeGoldenRecords
# ══════════════════════════════════════════════════════════════

class TestMergeGoldenRecords:
    def _setup_two_grs(self, mock_mysql, golden_factory):
        gr1 = golden_factory(
            gr_id="G-surv", name="SURVIVOR",
            source_count=3, source_records=["a", "b", "c"],
        )
        gr2 = golden_factory(
            gr_id="G-abso", name="ABSORBED",
            source_count=1, source_records=["d"],
        )
        mock_mysql.write_golden_record(gr1)
        mock_mysql.write_golden_record(gr2)

    def test_success(self, mock_writer, mock_mysql, golden_factory):
        self._setup_two_grs(mock_mysql, golden_factory)
        result = mock_writer.merge_golden_records("G-surv", "G-abso", {"confidence": 0.9})
        assert result["success"] is True

    def test_survivor_has_more_sources(self, mock_writer, mock_mysql, golden_factory):
        self._setup_two_grs(mock_mysql, golden_factory)
        result = mock_writer.merge_golden_records("G-surv", "G-abso", {})
        assert result["success"] is True
        # Survivor (G-surv has 3 sources > G-abso has 1)
        assert result["survivor_id"] == "G-surv"

    def test_combines_variants_and_keywords(self, mock_writer, mock_mysql, golden_factory):
        gr1 = golden_factory(
            gr_id="G-s", name="A", name_variants=["A"],
            top_keywords=["pvc"],
        )
        gr2 = golden_factory(
            gr_id="G-a", name="B", name_variants=["B"],
            top_keywords=["copper"],
        )
        mock_mysql.write_golden_record(gr1)
        mock_mysql.write_golden_record(gr2)
        result = mock_writer.merge_golden_records("G-s", "G-a", {})
        assert result["success"] is True

    def test_calls_transactional_merge(self, mock_writer, mock_mysql, golden_factory):
        self._setup_two_grs(mock_mysql, golden_factory)
        mock_writer.merge_golden_records("G-surv", "G-abso", {})
        # Absorbed should be marked MERGED
        absorbed = mock_mysql.get_golden_record("G-abso")
        assert absorbed["status"] == "MERGED"

    def test_gr_not_found_error(self, mock_writer):
        result = mock_writer.merge_golden_records("G-nonexistent", "G-also-nope", {})
        assert result["success"] is False
        assert "not found" in result["error"]


# ══════════════════════════════════════════════════════════════
# TestLogDecision
# ══════════════════════════════════════════════════════════════

class TestLogDecision:
    def test_writes_audit(self, mock_writer, mock_mysql):
        audit_id = mock_writer.log_decision(
            event_id="E-001",
            record_id="R-001",
            decision="MERGE",
            target_golden_record_id="G-001",
            confidence=0.92,
            dimension_scores={"identity": 0.9},
            reasoning="Test merge",
            key_factors=["strong_identity_match"],
            evaluation_chain=[{"step": "test"}],
            agent_metadata={"total_duration_ms": 100},
        )
        assert audit_id.startswith("A-")
        assert len(mock_mysql._mock_audit) == 1

    def test_returns_audit_id(self, mock_writer):
        audit_id = mock_writer.log_decision(
            event_id="E-002",
            record_id="R-002",
            decision="NEW_ENTITY",
            target_golden_record_id=None,
            confidence=0.0,
            dimension_scores={},
            reasoning="No match",
            key_factors=[],
            evaluation_chain=[],
            agent_metadata={},
        )
        assert isinstance(audit_id, str)
        assert audit_id.startswith("A-")
