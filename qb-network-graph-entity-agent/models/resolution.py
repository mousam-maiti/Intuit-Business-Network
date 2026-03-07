"""
Resolution request/response models — design doc §5.2 API contract.
"""
from __future__ import annotations
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field
from models.persona import ClassifiedPersona


class Decision(str, Enum):
    MERGE = "MERGE"
    NEW_ENTITY = "NEW_ENTITY"
    REVIEW = "REVIEW"
    NO_MERGE_FOUND = "NO_MERGE_FOUND"


class MatchLevel(str, Enum):
    """Which comparison layer produced the match."""
    EXACT = "EXACT"                     # EIN/phone/email exact
    DETERMINISTIC = "DETERMINISTIC"     # Jaro-Winkler > 0.85
    EMBEDDING = "EMBEDDING"             # Semantic similarity pushed above threshold
    LLM = "LLM"                         # LLM reasoning decided
    NONE = "NONE"


class DimensionConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"


# ── Request ─────────────────────────────────────────────────

class ResolutionRequest(BaseModel):
    event_id: str
    record_id: str
    record_type: str = "vendor"         # vendor | customer
    company_id: int
    chain_depth: int = 0
    classified_persona: ClassifiedPersona
    fast_mode: bool = False             # skip embedding + LLM, deterministic only


class ReEvaluationRequest(BaseModel):
    golden_record_id: str
    new_bucket_keys: list[str] = Field(default_factory=list)
    chain_depth: int = 1


# ── Per-dimension comparison result ─────────────────────────

class FieldMatchResult(str, Enum):
    EXACT = "EXACT"
    PARTIAL = "PARTIAL"
    DOMAIN_MATCH = "DOMAIN_MATCH"
    MISSING = "MISSING"
    MISMATCH = "MISMATCH"


class DimensionResult(BaseModel):
    score: float = 0.0
    confidence: DimensionConfidence = DimensionConfidence.INSUFFICIENT
    details: dict = Field(default_factory=dict)


class ComparisonResult(BaseModel):
    """Output of compare_fields — per-dimension scores + composite."""
    identity: DimensionResult = Field(default_factory=DimensionResult)
    industry: DimensionResult = Field(default_factory=DimensionResult)
    location: DimensionResult = Field(default_factory=DimensionResult)
    commodity: DimensionResult = Field(default_factory=DimensionResult)
    behavioral: DimensionResult = Field(default_factory=DimensionResult)
    composite: float = 0.0
    weights_used: dict[str, float] = Field(default_factory=dict)
    sparsity_adjusted: bool = False
    disqualified: bool = False
    disqualification_reason: Optional[str] = None


class SimilarityResult(BaseModel):
    """Output of semantic_similarity."""
    name_similarity: float = 0.0
    industry_similarity: float = 0.0
    commodity_similarity: float = 0.0
    location_similarity: float = 0.0
    composite_similarity: float = 0.0
    model_used: str = ""
    inference_ms: int = 0


class CandidateMatch(BaseModel):
    """A candidate golden record with all evaluation scores."""
    golden_record_id: str
    canonical_name: str
    comparison: Optional[ComparisonResult] = None
    similarity: Optional[SimilarityResult] = None
    combined_score: float = 0.0
    match_level: MatchLevel = MatchLevel.NONE
    disqualified: bool = False


# ── Evaluation chain step ───────────────────────────────────

class EvaluationStep(BaseModel):
    step: str
    tool_called: str = ""
    candidate: Optional[str] = None
    score: Optional[float] = None
    disqualified: Optional[bool] = None
    duration_ms: int = 0
    details: dict = Field(default_factory=dict)


# ── Response ────────────────────────────────────────────────

class DimensionScores(BaseModel):
    identity: float = 0.0
    industry: float = 0.0
    location: float = 0.0
    commodity: float = 0.0
    behavioral: float = 0.0


class ResolutionResponse(BaseModel):
    event_id: str
    decision: Decision
    target_golden_record_id: Optional[str] = None
    confidence: float = 0.0
    dimension_scores: DimensionScores = Field(default_factory=DimensionScores)
    reasoning: str = ""
    key_factors: list[str] = Field(default_factory=list)
    evaluation_chain: list[EvaluationStep] = Field(default_factory=list)
    agent_metadata: dict = Field(default_factory=dict)
    # Payload for Classifier Orchestrator to write to Paimon gold + sync to Neo4j
    golden_record_after: Optional[dict] = None
    relationship: Optional[dict] = None
    audit_record: Optional[dict] = None
    pending_resolution: Optional[dict] = None


class ReEvaluationResponse(BaseModel):
    golden_record_id: str
    merges: list[dict] = Field(default_factory=list)
    reviews: list[dict] = Field(default_factory=list)
    no_match_count: int = 0
    evaluation_chain: list[EvaluationStep] = Field(default_factory=list)
