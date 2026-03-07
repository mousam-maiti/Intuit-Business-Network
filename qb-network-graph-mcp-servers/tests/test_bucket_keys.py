"""Tests for utils/bucket_keys.py — bucket key generation from personas."""
import pytest
from models.persona import (
    ClassifiedPersona, IdentityDimension, IndustryDimension,
    LocationDimension, CommodityDimension, BehavioralDimension,
)
from utils.bucket_keys import generate_bucket_keys


class TestGenerateBucketKeys:
    """Test all 9 bucket key types generated from persona dimensions."""

    def _full_persona(self):
        return ClassifiedPersona(
            identity=IdentityDimension(
                normalized_name="Bob's Plumbing LLC",
                name_first_token="BOBS",
                name_tokens=["BOBS", "PLUMBING", "LLC"],
                ein_clean="743218976",
                phone_digits="5124551234",
                email="bob@bobsplumbing.com",
                email_domain="bobsplumbing.com",
            ),
            industry=IndustryDimension(
                naics_code="238220",
                naics_sector="23",
                naics_subsector="238",
                commodity_keywords=["pvc pipe", "copper fittings"],
            ),
            location=LocationDimension(
                state="TX",
                city_norm="AUSTIN",
                zip3="787",
                zip5="78704",
            ),
            commodity=CommodityDimension(
                top_keywords=["pvc pipe", "copper fittings", "plumbing supplies"],
            ),
        )

    def test_all_keys_generated(self):
        """Full persona should produce all 9+ bucket key types."""
        persona = self._full_persona()
        keys = generate_bucket_keys(persona)

        assert "name:BOBS+TX" in keys
        assert "ein:743218976" in keys
        assert "phone:5124551234" in keys
        assert "email_domain:bobsplumbing.com" in keys
        assert "naics3:238+TX" in keys
        assert "naics4:2382+TX" in keys
        assert "zip3:787" in keys
        assert "city:AUSTIN+TX" in keys
        assert "commodity:pvc pipe+TX" in keys
        assert "commodity:copper fittings+TX" in keys
        assert "commodity:plumbing supplies+TX" in keys

    def test_key_count(self):
        """Full persona should generate 11 keys (name, ein, phone, email_domain, naics3, naics4, zip3, city, 3 commodity)."""
        persona = self._full_persona()
        keys = generate_bucket_keys(persona)
        assert len(keys) == 11

    def test_max_commodity_kw_limits_output(self):
        """max_commodity_kw=1 should limit commodity keys."""
        persona = self._full_persona()
        keys = generate_bucket_keys(persona, max_commodity_kw=1)
        commodity_keys = [k for k in keys if k.startswith("commodity:")]
        assert len(commodity_keys) == 1
        assert commodity_keys[0] == "commodity:pvc pipe+TX"

    def test_max_commodity_kw_zero(self):
        """max_commodity_kw=0 should produce no commodity keys."""
        persona = self._full_persona()
        keys = generate_bucket_keys(persona, max_commodity_kw=0)
        commodity_keys = [k for k in keys if k.startswith("commodity:")]
        assert len(commodity_keys) == 0

    def test_name_requires_state(self):
        """name bucket key requires both name_first_token and state."""
        persona = ClassifiedPersona(
            identity=IdentityDimension(name_first_token="BOBS"),
            location=LocationDimension(state=""),  # no state
        )
        keys = generate_bucket_keys(persona)
        assert not any(k.startswith("name:") for k in keys)

    def test_name_key_uppercased(self):
        """name bucket key should uppercase the token."""
        persona = ClassifiedPersona(
            identity=IdentityDimension(name_first_token="bobs"),
            location=LocationDimension(state="tx"),
        )
        keys = generate_bucket_keys(persona)
        assert "name:BOBS+TX" in keys

    def test_ein_standalone(self):
        """EIN key does not need state."""
        persona = ClassifiedPersona(
            identity=IdentityDimension(ein_clean="123456789"),
            location=LocationDimension(state=""),
        )
        keys = generate_bucket_keys(persona)
        assert "ein:123456789" in keys

    def test_phone_standalone(self):
        """Phone key does not need state."""
        persona = ClassifiedPersona(
            identity=IdentityDimension(phone_digits="5125551234"),
            location=LocationDimension(state=""),
        )
        keys = generate_bucket_keys(persona)
        assert "phone:5125551234" in keys

    def test_email_domain_lowercase(self):
        """email_domain key should be lowercased."""
        persona = ClassifiedPersona(
            identity=IdentityDimension(email_domain="BobsPlumbing.COM"),
        )
        keys = generate_bucket_keys(persona)
        assert "email_domain:bobsplumbing.com" in keys

    def test_naics_requires_state(self):
        """naics3/naics4 keys require state."""
        persona = ClassifiedPersona(
            industry=IndustryDimension(naics_code="238220", naics_subsector="238"),
            location=LocationDimension(state=""),
        )
        keys = generate_bucket_keys(persona)
        assert not any(k.startswith("naics3:") for k in keys)
        assert not any(k.startswith("naics4:") for k in keys)

    def test_naics_code_too_short(self):
        """naics4 key requires at least 4-digit code."""
        persona = ClassifiedPersona(
            industry=IndustryDimension(naics_code="23", naics_subsector="23"),
            location=LocationDimension(state="TX"),
        )
        keys = generate_bucket_keys(persona)
        # naics4 should NOT be generated (code too short)
        assert not any(k.startswith("naics4:") for k in keys)
        # naics3 SHOULD be generated if subsector is set
        assert "naics3:23+TX" in keys

    def test_city_requires_state(self):
        """city key requires state."""
        persona = ClassifiedPersona(
            location=LocationDimension(city_norm="AUSTIN", state=""),
        )
        keys = generate_bucket_keys(persona)
        assert not any(k.startswith("city:") for k in keys)

    def test_city_uppercased(self):
        """city key uppercases city_norm."""
        persona = ClassifiedPersona(
            location=LocationDimension(city_norm="austin", state="TX"),
        )
        keys = generate_bucket_keys(persona)
        assert "city:AUSTIN+TX" in keys

    def test_zip3_standalone(self):
        """zip3 key doesn't need state."""
        persona = ClassifiedPersona(
            location=LocationDimension(zip3="787", state=""),
        )
        keys = generate_bucket_keys(persona)
        assert "zip3:787" in keys

    def test_commodity_requires_state(self):
        """commodity keys require state."""
        persona = ClassifiedPersona(
            commodity=CommodityDimension(top_keywords=["pvc pipe"]),
            location=LocationDimension(state=""),
        )
        keys = generate_bucket_keys(persona)
        assert not any(k.startswith("commodity:") for k in keys)

    def test_commodity_lowercased(self):
        """commodity keywords should be lowercased."""
        persona = ClassifiedPersona(
            commodity=CommodityDimension(top_keywords=["PVC PIPE"]),
            location=LocationDimension(state="TX"),
        )
        keys = generate_bucket_keys(persona)
        assert "commodity:pvc pipe+TX" in keys

    def test_empty_persona(self):
        """Empty persona should produce no keys."""
        persona = ClassifiedPersona()
        keys = generate_bucket_keys(persona)
        assert keys == []

    def test_none_fields_handled(self):
        """None in optional fields should not cause errors."""
        persona = ClassifiedPersona(
            identity=IdentityDimension(
                ein_clean=None,
                phone_digits=None,
                email_domain=None,
            ),
            industry=IndustryDimension(naics_code=None, naics_subsector=None),
            location=LocationDimension(state="", city_norm=None, zip3=None),
            commodity=CommodityDimension(top_keywords=[]),
        )
        keys = generate_bucket_keys(persona)
        assert keys == []

    def test_state_case_handling(self):
        """State should be uppercased from lowercase input."""
        persona = ClassifiedPersona(
            identity=IdentityDimension(name_first_token="BOBS"),
            location=LocationDimension(state="tx"),
        )
        keys = generate_bucket_keys(persona)
        assert "name:BOBS+TX" in keys
