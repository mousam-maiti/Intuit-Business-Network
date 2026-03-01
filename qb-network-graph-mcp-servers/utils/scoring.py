"""
Scoring utilities — deterministic field comparison logic.
Design doc §2.1 compare_fields implementation detail.

All scoring is pure computation — no I/O, no API calls.
The only exception is industry scoring which *may* call
query_ontology for cross-taxonomy links; that's handled
by the caller (compare_fields) not here.
"""
from __future__ import annotations
from rapidfuzz.distance import JaroWinkler
from models.persona import ClassifiedPersona, GoldenRecord
from models.resolution import (
    ComparisonResult, DimensionResult, DimensionConfidence, FieldMatchResult,
)


# ── String similarity ───────────────────────────────────────

def jaro_winkler(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return JaroWinkler.normalized_similarity(a.upper(), b.upper())


def jaccard_tokens(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    if not a or not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / len(union)


def jaccard_keywords(a: list[str], b: list[str]) -> float:
    sa = {k.lower().strip() for k in a if k}
    sb = {k.lower().strip() for k in b if k}
    return jaccard_tokens(sa, sb)


# ── EIN / Phone / Email matching ────────────────────────────

def match_ein(a: str | None, b: str | None) -> FieldMatchResult:
    if not a or not b:
        return FieldMatchResult.MISSING
    return FieldMatchResult.EXACT if a.strip() == b.strip() else FieldMatchResult.MISMATCH


def match_phone(a: str | None, b: str | None) -> FieldMatchResult:
    if not a or not b:
        return FieldMatchResult.MISSING
    if a == b:
        return FieldMatchResult.EXACT
    # last 7 digits match = partial
    if len(a) >= 7 and len(b) >= 7 and a[-7:] == b[-7:]:
        return FieldMatchResult.PARTIAL
    return FieldMatchResult.MISMATCH


def match_email(a: str | None, b: str | None) -> FieldMatchResult:
    if not a or not b:
        return FieldMatchResult.MISSING
    a_lower, b_lower = a.lower().strip(), b.lower().strip()
    if a_lower == b_lower:
        return FieldMatchResult.EXACT
    a_domain = a_lower.split("@")[-1] if "@" in a_lower else ""
    b_domain = b_lower.split("@")[-1] if "@" in b_lower else ""
    if a_domain and b_domain and a_domain == b_domain:
        return FieldMatchResult.DOMAIN_MATCH
    return FieldMatchResult.MISMATCH


# ── Identity dimension ──────────────────────────────────────

def score_identity(
    orphan: ClassifiedPersona,
    candidate_persona: ClassifiedPersona,
    candidate_name_variants: list[str],
) -> DimensionResult:
    oi, ci = orphan.identity, candidate_persona.identity

    ein_result = match_ein(oi.ein_clean, ci.ein_clean)
    phone_result = match_phone(oi.phone_digits, ci.phone_digits)
    email_result = match_email(oi.email, ci.email)
    name_sim = jaro_winkler(oi.normalized_name, ci.normalized_name)
    orphan_tokens = {t.upper() for t in oi.name_tokens if t}
    cand_tokens = {t.upper() for t in ci.name_tokens if t}
    token_overlap = jaccard_tokens(orphan_tokens, cand_tokens)

    # Check if orphan name is in candidate's known variants
    orphan_norm = oi.normalized_name.upper().strip()
    name_in_variants = orphan_norm in {v.upper().strip() for v in candidate_name_variants}

    # Score = max of all identity signals (design doc)
    signals = [name_sim, token_overlap]
    if name_in_variants:
        signals.append(1.0)
    if ein_result == FieldMatchResult.EXACT:
        signals.append(1.0)
    if phone_result == FieldMatchResult.EXACT:
        signals.append(0.9)
    if phone_result == FieldMatchResult.PARTIAL:
        signals.append(0.6)
    if email_result == FieldMatchResult.EXACT:
        signals.append(0.9)
    if email_result == FieldMatchResult.DOMAIN_MATCH:
        signals.append(0.5)

    score = max(signals) if signals else 0.0

    # Count available fields for confidence
    available = sum(1 for x in [
        oi.normalized_name, oi.ein_clean, oi.phone_digits, oi.email,
    ] if x)
    conf = (
        DimensionConfidence.HIGH if available >= 3
        else DimensionConfidence.MEDIUM if available >= 2
        else DimensionConfidence.LOW if available >= 1
        else DimensionConfidence.INSUFFICIENT
    )

    return DimensionResult(
        score=round(score, 3),
        confidence=conf,
        details={
            "ein_match": ein_result.value,
            "phone_match": phone_result.value,
            "email_match": email_result.value,
            "name_similarity": round(name_sim, 3),
            "name_token_overlap": round(token_overlap, 3),
            "name_in_variants": name_in_variants,
        },
    )


# ── Industry dimension ──────────────────────────────────────

def score_industry(
    orphan: ClassifiedPersona,
    candidate_persona: ClassifiedPersona,
    ontology_score: float | None = None,
) -> DimensionResult:
    """Score industry match. ontology_score is provided by caller
    if NAICS sectors differ and query_ontology was called."""
    oi, ci = orphan.industry, candidate_persona.industry

    if not oi.naics_code and not ci.naics_code:
        return DimensionResult(
            score=0.0,
            confidence=DimensionConfidence.INSUFFICIENT,
            details={"reason": "both_missing"},
        )

    if not oi.naics_code or not ci.naics_code:
        return DimensionResult(
            score=0.0,
            confidence=DimensionConfidence.INSUFFICIENT,
            details={"reason": "one_missing"},
        )

    # Exact match
    if oi.naics_code == ci.naics_code:
        return DimensionResult(
            score=1.0,
            confidence=DimensionConfidence.HIGH,
            details={"naics_exact": True},
        )

    # Subsector match (first 3 digits)
    o_sub = oi.naics_code[:3] if len(oi.naics_code) >= 3 else ""
    c_sub = ci.naics_code[:3] if len(ci.naics_code) >= 3 else ""
    if o_sub and c_sub and o_sub == c_sub:
        return DimensionResult(
            score=0.8,
            confidence=DimensionConfidence.HIGH,
            details={"naics_subsector_match": True, "subsector": o_sub},
        )

    # Sector match (first 2 digits)
    o_sec = oi.naics_code[:2] if len(oi.naics_code) >= 2 else ""
    c_sec = ci.naics_code[:2] if len(ci.naics_code) >= 2 else ""
    if o_sec and c_sec and o_sec == c_sec:
        return DimensionResult(
            score=0.5,
            confidence=DimensionConfidence.MEDIUM,
            details={"naics_sector_match": True, "sector": o_sec},
        )

    # Different sectors — use ontology result if provided
    if ontology_score is not None:
        return DimensionResult(
            score=round(ontology_score, 3),
            confidence=DimensionConfidence.MEDIUM if ontology_score > 0.2 else DimensionConfidence.LOW,
            details={
                "naics_sector_match": False,
                "ontology_consulted": True,
                "ontology_score": round(ontology_score, 3),
            },
        )

    # No ontology — conservative 0.0
    return DimensionResult(
        score=0.0,
        confidence=DimensionConfidence.LOW,
        details={"naics_sector_match": False, "ontology_consulted": False},
    )


# ── Location dimension ──────────────────────────────────────

def score_location(
    orphan: ClassifiedPersona,
    candidate_persona: ClassifiedPersona,
) -> DimensionResult:
    ol, cl = orphan.location, candidate_persona.location

    if not ol.state or not cl.state:
        return DimensionResult(
            score=0.0,
            confidence=DimensionConfidence.INSUFFICIENT,
            details={"reason": "state_missing"},
        )

    # State must match (or one null — handled above)
    if ol.state.upper() != cl.state.upper():
        # Hard disqualifier at the comparison level — caller checks
        return DimensionResult(
            score=0.0,
            confidence=DimensionConfidence.HIGH,
            details={"state_match": False},
        )

    # ZIP5
    if ol.zip5 and cl.zip5 and ol.zip5 == cl.zip5:
        return DimensionResult(
            score=1.0, confidence=DimensionConfidence.HIGH,
            details={"state_match": True, "zip5_match": True},
        )

    # ZIP3
    if ol.zip3 and cl.zip3 and ol.zip3 == cl.zip3:
        return DimensionResult(
            score=0.8, confidence=DimensionConfidence.HIGH,
            details={"state_match": True, "zip3_match": True},
        )

    # City
    if ol.city_norm and cl.city_norm:
        if ol.city_norm.upper() == cl.city_norm.upper():
            return DimensionResult(
                score=0.7, confidence=DimensionConfidence.MEDIUM,
                details={"state_match": True, "city_match": True},
            )

    # State only
    return DimensionResult(
        score=0.3, confidence=DimensionConfidence.LOW,
        details={"state_match": True, "city_match": False},
    )


# ── Commodity dimension ─────────────────────────────────────

def score_commodity(
    orphan: ClassifiedPersona,
    candidate_persona: ClassifiedPersona,
) -> DimensionResult:
    o_kw = orphan.commodity.top_keywords
    c_kw = candidate_persona.commodity.top_keywords

    if not o_kw and not c_kw:
        return DimensionResult(
            score=0.0, confidence=DimensionConfidence.INSUFFICIENT,
            details={"reason": "both_empty"},
        )
    if not o_kw or not c_kw:
        return DimensionResult(
            score=0.0, confidence=DimensionConfidence.INSUFFICIENT,
            details={"reason": "one_empty"},
        )

    overlap = jaccard_keywords(o_kw, c_kw)
    o_set = {k.lower() for k in o_kw}
    c_set = {k.lower() for k in c_kw}
    shared = sorted(o_set & c_set)

    conf = (
        DimensionConfidence.HIGH if overlap > 0.6
        else DimensionConfidence.MEDIUM if overlap > 0.3
        else DimensionConfidence.LOW
    )

    return DimensionResult(
        score=round(overlap, 3), confidence=conf,
        details={"keyword_overlap": round(overlap, 3), "overlapping_keywords": shared},
    )


# ── Behavioral dimension ────────────────────────────────────

def score_behavioral(
    orphan: ClassifiedPersona,
    candidate_persona: ClassifiedPersona,
) -> DimensionResult:
    ob, cb = orphan.behavioral, candidate_persona.behavioral

    if not ob.volume_bracket or not cb.volume_bracket:
        return DimensionResult(
            score=0.0, confidence=DimensionConfidence.INSUFFICIENT,
            details={"reason": "bracket_missing"},
        )

    bracket_match = ob.volume_bracket == cb.volume_bracket
    score = 0.7 if bracket_match else 0.3

    # Volume ratio check (within 10x)
    if ob.avg_transaction and cb.avg_transaction and cb.avg_transaction > 0:
        ratio = ob.avg_transaction / cb.avg_transaction
        if 0.1 <= ratio <= 10.0:
            score = max(score, 0.6)
        else:
            score = min(score, 0.2)

    conf = DimensionConfidence.MEDIUM if bracket_match else DimensionConfidence.LOW

    return DimensionResult(
        score=round(score, 3), confidence=conf,
        details={
            "volume_bracket_match": bracket_match,
            "orphan_bracket": ob.volume_bracket,
            "candidate_bracket": cb.volume_bracket,
        },
    )


# ── Composite scoring with adaptive weights ─────────────────

def compute_composite(
    dimensions: dict[str, DimensionResult],
    base_weights: dict[str, float],
) -> tuple[float, dict[str, float], bool]:
    """Compute weighted composite score with adaptive weight redistribution.

    If a dimension has INSUFFICIENT data, its weight is redistributed
    proportionally to dimensions that have data.

    Returns: (composite_score, weights_used, sparsity_adjusted)
    """
    available: dict[str, float] = {}
    insufficient_weight = 0.0

    for dim_name, weight in base_weights.items():
        result = dimensions.get(dim_name)
        if result and result.confidence != DimensionConfidence.INSUFFICIENT:
            available[dim_name] = weight
        else:
            insufficient_weight += weight

    if not available:
        return 0.0, base_weights, False

    sparsity_adjusted = insufficient_weight > 0.0
    total_available_weight = sum(available.values())

    # Redistribute insufficient weight proportionally
    adjusted: dict[str, float] = {}
    for dim_name, weight in available.items():
        proportion = weight / total_available_weight
        adjusted[dim_name] = weight + (insufficient_weight * proportion)

    # Compute weighted score
    composite = 0.0
    for dim_name, adj_weight in adjusted.items():
        composite += dimensions[dim_name].score * adj_weight

    # Identity floor cap: if identity scored below 0.55 and identity data
    # is available, cap composite at 0.70 to prevent "same industry competitor"
    # patterns from reaching high-confidence territory.
    identity_dim = dimensions.get("identity")
    if (identity_dim
            and identity_dim.confidence != DimensionConfidence.INSUFFICIENT
            and identity_dim.score < 0.55):
        composite = min(composite, 0.70)

    return round(composite, 4), {k: round(v, 4) for k, v in adjusted.items()}, sparsity_adjusted
