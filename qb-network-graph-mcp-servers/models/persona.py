"""
Classified Persona & Golden Record models — design doc §5.2.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── Persona dimensions ──────────────────────────────────────

class IdentityDimension(BaseModel):
    normalized_name: str = Field(default="", alias="canonical_name")
    name_first_token: str = ""
    name_tokens: list[str] = Field(default_factory=list)
    legal_suffix: Optional[str] = None
    ein_clean: Optional[str] = None
    phone_digits: Optional[str] = None
    email: Optional[str] = None
    email_domain: Optional[str] = None

    model_config = {"populate_by_name": True}


class IndustryDimension(BaseModel):
    naics_code: Optional[str] = None
    naics_sector: Optional[str] = None
    naics_subsector: Optional[str] = None
    original_category: Optional[str] = None
    commodity_keywords: list[str] = Field(default_factory=list)


class LocationDimension(BaseModel):
    state: str = ""
    city_norm: Optional[str] = None
    zip3: Optional[str] = None
    zip5: Optional[str] = None


class CommodityDimension(BaseModel):
    top_keywords: list[str] = Field(default_factory=list)
    service_categories: list[str] = Field(default_factory=list)


class BehavioralDimension(BaseModel):
    volume_bracket: Optional[str] = None
    avg_transaction: Optional[float] = None
    transaction_count: Optional[int] = None
    payment_terms: Optional[str] = None


class SparsityScores(BaseModel):
    identity: int = 0
    industry: int = 0
    location: int = 0
    commodity: int = 0
    behavioral: int = 0


class ClassifiedPersona(BaseModel):
    identity: IdentityDimension = Field(default_factory=IdentityDimension)
    industry: IndustryDimension = Field(default_factory=IndustryDimension)
    location: LocationDimension = Field(default_factory=LocationDimension)
    commodity: CommodityDimension = Field(default_factory=CommodityDimension)
    behavioral: BehavioralDimension = Field(default_factory=BehavioralDimension)
    sparsity: SparsityScores = Field(default_factory=SparsityScores)


# ── Golden Record ───────────────────────────────────────────

class GoldenRecord(BaseModel):
    golden_record_id: str
    canonical_name: str
    name_variants: list[str] = Field(default_factory=list)
    persona: ClassifiedPersona = Field(default_factory=ClassifiedPersona)
    source_count: int = 1
    confidence: float = 0.5
    status: str = "ACTIVE"                  # ACTIVE | PROVISIONAL | MERGED
    merged_into: Optional[str] = None
    entity_type: str = "PHANTOM"            # QB_USER | PHANTOM
    source_records: list[str] = Field(default_factory=list)
    bucket_keys: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
