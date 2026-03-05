"""Pydantic response/request models matching the UI entity shape."""
from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel


# ── Entity (matches UI ENTITIES shape) ───────────────────

class Entity(BaseModel):
    id: str
    name: str
    ein: Optional[str] = None
    contactName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    naics: Optional[str] = None
    legalStructure: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    confidence: Optional[float] = None
    vendors: int = 0
    clients: int = 0
    volume: Optional[float] = None
    variants: list[str] = []
    commodities: list[str] = []
    serviceArea: Optional[str] = None


# ── Relationship ─────────────────────────────────────────

class Relationship(BaseModel):
    source: str
    target: str
    volume: Optional[float] = None
    count: Optional[int] = None
    status: Optional[str] = None


# ── Network graph ────────────────────────────────────────

class NetworkGraph(BaseModel):
    entities: list[Entity]
    relationships: list[Relationship]


# ── Monthly volume ───────────────────────────────────────

class MonthlyVolume(BaseModel):
    month: str
    vol: float


# ── Pending match ────────────────────────────────────────

class PendingMatch(BaseModel):
    id: str
    inputName: Optional[str] = None
    inputCategory: Optional[str] = None
    inputLocation: Optional[str] = None
    candidate: Optional[Entity] = None
    confidence: Optional[float] = None
    age: Optional[str] = None
    scores: Optional[dict] = None
    sharedNeighbors: list[str] = []
    triggerType: Optional[str] = "AI_AGENT"


# ── Match resolution request ────────────────────────────

class ResolveRequest(BaseModel):
    resolution: str  # "accept" | "reject"
    candidateGoldenId: Optional[str] = None  # Override: merge into this instead of AI-suggested


class AdHocResolveRequest(BaseModel):
    name: Optional[str] = None
    ein: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    industry: Optional[str] = None


# ── Connections ──────────────────────────────────────────

class AutoConnection(BaseModel):
    id: str
    type: str
    source: Optional[str] = None
    sourceDate: Optional[str] = None
    entity: Optional[Entity] = None
    resolution: Optional[str] = None
    tier: Optional[int] = None
    confidence: Optional[float] = None
    latency: Optional[str] = None
    time: Optional[str] = None


class ManualConnection(BaseModel):
    id: str
    type: str
    entity: Optional[Any] = None
    addedVia: Optional[str] = None
    confidence: Optional[float] = None
    time: Optional[str] = None


class AddConnectionRequest(BaseModel):
    connType: str
    entity: Optional[dict] = None
    name: Optional[str] = None
    ein: Optional[str] = None
    contactName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    category: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    commodity: Optional[str] = None
    expectedVolume: Optional[str] = None
    paymentTerms: Optional[str] = None


# ── Native overrides ────────────────────────────────────

class NativeOverrideUpdate(BaseModel):
    """Arbitrary fields to merge into overrides."""
    class Config:
        extra = "allow"


# ── Native merges ───────────────────────────────────────

class NativeMerge(BaseModel):
    id: str
    sourceEntityId: str
    targetEntityId: str
    origin: str = "user"
    reason: Optional[str] = None
    migratedRelationships: list[dict] = []
    timestamp: Optional[str] = None


class CreateMergeRequest(BaseModel):
    sourceEntityId: str
    targetEntityId: str
    reason: Optional[str] = None
    migratedRelationships: list[dict] = []


# ── Patch entity request ────────────────────────────────

class PatchEntityRequest(BaseModel):
    class Config:
        extra = "allow"
