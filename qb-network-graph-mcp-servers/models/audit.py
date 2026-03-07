"""
Audit models — every agent invocation produces an audit record.
Design doc §2.3 entity_writer.log_decision.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class AuditRecord(BaseModel):
    audit_id: str
    event_id: str
    record_id: str
    perspective: str = "GLOBAL"
    decision: str                       # MERGE | NEW_ENTITY | REVIEW | NO_MERGE_FOUND
    trigger_type: str = ""              # LAYER_1_EIN | AI_AGENT_EMBEDDING | AI_AGENT_LLM
    target_golden_id: Optional[str] = None
    absorbed_golden_id: Optional[str] = None
    confidence: float = 0.0
    dimension_scores: dict = Field(default_factory=dict)
    reasoning: str = ""
    key_factors: list[str] = Field(default_factory=list)
    candidates_evaluated: int = 0
    llm_calls: int = 0
    embedding_calls: int = 0
    total_duration_ms: int = 0
    evaluation_chain: list[dict] = Field(default_factory=list)
    golden_record_before: Optional[dict] = None
    golden_record_after: Optional[dict] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class PendingResolution(BaseModel):
    match_id: str
    orphan_golden_id: str
    candidate_golden_id: str
    confidence: float = 0.0
    dimension_scores: dict = Field(default_factory=dict)
    reasoning: str = ""
    key_uncertainty: str = ""
    trigger_type: str = "AI_AGENT"
    status: str = "PENDING"             # PENDING | MERGED | REJECTED
    company_id: Optional[str] = None    # QB company that owns the source record
    record_type: Optional[str] = None   # "vendor" or "customer"
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
