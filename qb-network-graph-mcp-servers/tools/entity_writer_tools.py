"""
Entity writer tools — extracted from EntityWriter.

5 tools: merge_into_golden_record, create_golden_record, submit_for_review,
         merge_golden_records, log_decision

Primary store: Neo4j (real-time graph).
Pending resolution: MySQL (OLTP work queue).
Paimon gold writes: handled by the classifier orchestrator after /resolve.
"""
from __future__ import annotations
import logging
import time
import uuid

from mcp.server.fastmcp import Context

from app import mcp, AppContext
from models.persona import GoldenRecord, ClassifiedPersona
from models.audit import AuditRecord, PendingResolution
from utils.bucket_keys import generate_bucket_keys

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────

def _to_classified_persona(data: dict) -> ClassifiedPersona:
    if isinstance(data, ClassifiedPersona):
        return data
    try:
        return ClassifiedPersona.model_validate(data)
    except Exception:
        return ClassifiedPersona()


def _apply_survivorship(gr: GoldenRecord, orphan: ClassifiedPersona):
    gi, oi = gr.persona.identity, orphan.identity
    if not gi.ein_clean and oi.ein_clean:
        gi.ein_clean = oi.ein_clean
    if not gi.phone_digits and oi.phone_digits:
        gi.phone_digits = oi.phone_digits
    if not gi.email and oi.email:
        gi.email = oi.email
        gi.email_domain = oi.email_domain

    gind, oind = gr.persona.industry, orphan.industry
    if oind.naics_code and (not gind.naics_code or len(oind.naics_code) > len(gind.naics_code)):
        gind.naics_code = oind.naics_code
        gind.naics_sector = oind.naics_sector
        gind.naics_subsector = oind.naics_subsector

    gl, ol = gr.persona.location, orphan.location
    if not gl.city_norm and ol.city_norm:
        gl.city_norm = ol.city_norm
    if not gl.zip5 and ol.zip5:
        gl.zip5 = ol.zip5
    if not gl.zip3 and ol.zip3:
        gl.zip3 = ol.zip3

    existing_kw = {k.lower() for k in gr.persona.commodity.top_keywords}
    for kw in orphan.commodity.top_keywords:
        if kw.lower() not in existing_kw:
            gr.persona.commodity.top_keywords.append(kw)
            existing_kw.add(kw.lower())


def _resolve_canonical_name(persona: ClassifiedPersona) -> str:
    name = persona.identity.normalized_name
    if not name:
        name = getattr(persona.identity, 'canonical_name', '') or ''
    if not name and persona.identity.name_first_token:
        name = persona.identity.name_first_token
    return name


def _get_volume(persona: ClassifiedPersona):
    """Estimate total volume from persona behavioral data."""
    b = persona.behavioral
    if b.avg_transaction and b.transaction_count:
        return round(b.avg_transaction * b.transaction_count, 2)
    return None


def _get_txn_count(persona: ClassifiedPersona):
    """Extract transaction count from persona."""
    return persona.behavioral.transaction_count


def _ensure_company_golden_record(app: "AppContext", company_id: str):
    """Create a QB_USER golden record for a company if it doesn't already exist.

    Reads company data from MySQL (source), writes golden record to Neo4j (primary).
    """
    cid = str(company_id)
    existing = app.neo4j.get_golden_record(cid)
    if existing:
        return
    company = app.mysql.get_company(cid)
    name = company["company_name"] if company else f"Company {cid}"

    persona = ClassifiedPersona()
    if company:
        ein_raw = company.get("ein") or ""
        ein_clean = ein_raw.replace("-", "").strip() or None
        persona.identity.normalized_name = name
        persona.identity.name_first_token = name.split()[0].upper() if name else ""
        persona.identity.name_tokens = [t.upper() for t in name.split()] if name else []
        persona.identity.ein_clean = ein_clean
        persona.identity.phone_digits = (company.get("phone") or "").replace("-", "").replace(" ", "")[-10:] or None
        persona.identity.email = company.get("email")
        persona.identity.email_domain = (company.get("email") or "").split("@")[-1] if company.get("email") else None

        persona.location.state = company.get("state") or ""
        persona.location.city_norm = (company.get("city") or "").upper() or None
        zip_val = company.get("zip") or ""
        persona.location.zip5 = zip_val[:5] if len(zip_val) >= 5 else None
        persona.location.zip3 = zip_val[:3] if len(zip_val) >= 3 else None

        persona.industry.original_category = company.get("industry_category")

    bucket_keys = generate_bucket_keys(persona, app.config.buckets.max_commodity_keywords)

    gr = GoldenRecord(
        golden_record_id=cid,
        canonical_name=name,
        name_variants=[name],
        persona=persona,
        source_count=1,
        confidence=1.0,
        status="ACTIVE",
        entity_type="QB_USER",
        source_records=[],
        bucket_keys=bucket_keys,
    )
    app.neo4j.upsert_entity(gr.model_dump())


async def _invalidate_cache(app: "AppContext", *entity_ids: str):
    """Invalidate Redis cache for affected entities."""
    if not app.redis.available:
        return
    for eid in entity_ids:
        await app.redis.invalidate_entity(eid)


# ── Tool 8: merge_into_golden_record ────────────────────────

@mcp.tool()
async def merge_into_golden_record(
    orphan_record_id: str,
    orphan_persona: dict,
    golden_record_id: str,
    merge_reasoning: dict,
    company_id: str = None,
    record_type: str = "vendor",
    ctx: Context = None,
) -> dict:
    """Merge an orphan record into an existing golden record.

    Applies survivorship rules (fill-in-the-blanks), updates the golden record
    in Neo4j (primary store), syncs to Milvus vectors.

    Args:
        orphan_record_id: Record ID of the orphan being merged.
        orphan_persona: Classified persona dict of the orphan.
        golden_record_id: Target golden record to merge into.
        merge_reasoning: Dict with reasoning, confidence, dimension_scores.
        company_id: Optional company ID to create a relationship edge.
        record_type: Type of record — 'vendor' or 'customer' (default 'vendor').

    Returns:
        Dict with 'success', 'golden_record_id', before/after snapshots, sync_status.
    """
    app: AppContext = ctx.request_context.lifespan_context
    start = time.time()

    gr_data = app.neo4j.get_golden_record(golden_record_id)
    if not gr_data:
        return {"success": False, "error": f"Golden record {golden_record_id} not found"}

    before_snapshot = dict(gr_data)
    gr = GoldenRecord.model_validate(gr_data)
    persona = _to_classified_persona(orphan_persona)
    _apply_survivorship(gr, persona)

    orphan_name = persona.identity.normalized_name
    if orphan_name and orphan_name.upper() not in {v.upper() for v in gr.name_variants}:
        gr.name_variants.append(orphan_name)

    gr.source_count += 1
    gr.source_records.append(orphan_record_id)
    gr.bucket_keys = generate_bucket_keys(gr.persona, app.config.buckets.max_commodity_keywords)
    gr.confidence = min(0.99, gr.confidence + 0.05)

    app.neo4j.upsert_entity(gr.model_dump())

    # Relationship edge: company is always the source
    #   vendor:   Company -[:BUYS_FROM]-> Vendor
    #   customer: Company -[:SELLS_TO]-> Customer
    relationship = None
    if company_id is not None:
        _ensure_company_golden_record(app, company_id)
        src, tgt = str(company_id), gr.golden_record_id
        edge_id = app.neo4j.generate_id("E")
        volume = _get_volume(persona)
        count = _get_txn_count(persona)
        rel_type = "SELLS_TO" if record_type == "customer" else "BUYS_FROM"
        app.neo4j.create_relationship(
            source_id=src, target_id=tgt, rel_type=rel_type,
            properties={"volume": volume, "count": count, "edge_id": edge_id},
        )
        relationship = {
            "edge_id": edge_id, "source_entity_id": src, "target_entity_id": tgt,
            "rel_type": rel_type, "transaction_volume": volume, "transaction_count": count,
        }

    milvus_result = app.milvus.upsert_golden_record(gr.model_dump())

    invalidate_ids = [gr.golden_record_id]
    if company_id is not None:
        invalidate_ids.extend([src, tgt])
    await _invalidate_cache(app, *invalidate_ids)

    elapsed = int((time.time() - start) * 1000)
    return {
        "success": True,
        "golden_record_id": gr.golden_record_id,
        "golden_record_before": before_snapshot,
        "golden_record_after": gr.model_dump(),
        "relationship": relationship,
        "sync_status": {"neo4j": True, "milvus": milvus_result.get("success", False),
                        "redis_invalidated": app.redis.available},
        "duration_ms": elapsed,
    }


# ── Tool 9: create_golden_record ────────────────────────────

@mcp.tool()
async def create_golden_record(
    orphan_record_id: str,
    orphan_persona: dict,
    creation_reasoning: dict,
    company_id: str = None,
    record_type: str = "vendor",
    ctx: Context = None,
) -> dict:
    """Create a new golden record from an unmatched orphan.

    Generates a new golden record ID, builds bucket keys, persists to Neo4j
    (primary store), syncs vectors to Milvus.

    Args:
        orphan_record_id: Record ID of the orphan.
        orphan_persona: Classified persona dict of the orphan.
        creation_reasoning: Dict with reasoning for why this is a new entity.
        company_id: Optional company ID to create a relationship edge.
        record_type: Type of record — 'vendor' or 'customer' (default 'vendor').

    Returns:
        Dict with 'success', 'golden_record_id', 'bucket_keys', sync_status.
    """
    app: AppContext = ctx.request_context.lifespan_context
    start = time.time()

    persona = _to_classified_persona(orphan_persona)
    gr_id = app.neo4j.generate_id("G")
    name = _resolve_canonical_name(persona)

    gr = GoldenRecord(
        golden_record_id=gr_id,
        canonical_name=name,
        name_variants=[name] if name else [],
        persona=persona,
        source_count=1,
        confidence=0.5,
        status="ACTIVE",
        entity_type="PHANTOM",
        source_records=[orphan_record_id],
        bucket_keys=generate_bucket_keys(persona, app.config.buckets.max_commodity_keywords),
    )

    app.neo4j.upsert_entity(gr.model_dump())

    # Relationship edge: vendor = company→entity, customer = entity→company
    # Relationship edge: company is always the source
    relationship = None
    if company_id is not None:
        _ensure_company_golden_record(app, company_id)
        src, tgt = str(company_id), gr_id
        edge_id = app.neo4j.generate_id("E")
        volume = _get_volume(persona)
        count = _get_txn_count(persona)
        rel_type = "SELLS_TO" if record_type == "customer" else "BUYS_FROM"
        app.neo4j.create_relationship(
            source_id=src, target_id=tgt, rel_type=rel_type,
            properties={"volume": volume, "count": count, "edge_id": edge_id},
        )
        relationship = {
            "edge_id": edge_id, "source_entity_id": src, "target_entity_id": tgt,
            "rel_type": rel_type, "transaction_volume": volume, "transaction_count": count,
        }

    milvus_result = app.milvus.upsert_golden_record(gr.model_dump())

    if company_id is not None:
        await _invalidate_cache(app, str(company_id))

    elapsed = int((time.time() - start) * 1000)
    return {
        "success": True,
        "golden_record_id": gr_id,
        "golden_record_after": gr.model_dump(),
        "bucket_keys": gr.bucket_keys,
        "relationship": relationship,
        "sync_status": {"neo4j": True, "milvus": milvus_result.get("success", False),
                        "redis_invalidated": app.redis.available},
        "duration_ms": elapsed,
    }


# ── Tool 10: submit_for_review ──────────────────────────────

@mcp.tool()
async def submit_for_review(
    orphan_record_id: str,
    orphan_persona: dict,
    candidate_golden_record_id: str,
    review_reasoning: dict,
    company_id: str = None,
    record_type: str = "vendor",
    ctx: Context = None,
) -> dict:
    """Submit an ambiguous match to the human review queue.

    Creates a provisional golden record in Neo4j and a pending resolution
    entry in MySQL (OLTP work queue).

    Args:
        orphan_record_id: Record ID of the orphan.
        orphan_persona: Classified persona dict of the orphan.
        candidate_golden_record_id: Best candidate golden record ID.
        review_reasoning: Dict with confidence, dimension_scores, reasoning, key_uncertainty.
        company_id: Optional company ID to create a relationship edge.
        record_type: Type of record — 'vendor' or 'customer' (default 'vendor').

    Returns:
        Dict with 'success', 'provisional_golden_record_id', 'pending_match_id', sync_status.
    """
    app: AppContext = ctx.request_context.lifespan_context
    start = time.time()

    persona = _to_classified_persona(orphan_persona)
    prov_id = app.neo4j.generate_id("G")
    name = _resolve_canonical_name(persona)
    prov_gr = GoldenRecord(
        golden_record_id=prov_id,
        canonical_name=name,
        name_variants=[name] if name else [],
        persona=persona,
        source_count=1,
        confidence=review_reasoning.get("confidence", 0.5),
        status="PROVISIONAL",
        entity_type="PHANTOM",
        source_records=[orphan_record_id],
        bucket_keys=generate_bucket_keys(persona, app.config.buckets.max_commodity_keywords),
    )

    # Write provisional GR to Neo4j (primary)
    app.neo4j.upsert_entity(prov_gr.model_dump())

    # Write pending resolution to MySQL (OLTP work queue)
    match_id = f"PR-{uuid.uuid4().hex[:8]}"
    pending = PendingResolution(
        match_id=match_id,
        orphan_golden_id=prov_id,
        candidate_golden_id=candidate_golden_record_id,
        confidence=review_reasoning.get("confidence", 0.5),
        dimension_scores=review_reasoning.get("dimension_scores", {}),
        reasoning=review_reasoning.get("reasoning", ""),
        key_uncertainty=review_reasoning.get("key_uncertainty", ""),
        trigger_type=review_reasoning.get("trigger_type", "AI_AGENT"),
    )
    app.mysql.write_pending_resolution(pending)

    # Relationship edge: vendor = company→entity, customer = entity→company
    # Relationship edge: company is always the source
    relationship = None
    if company_id is not None:
        _ensure_company_golden_record(app, company_id)
        src, tgt = str(company_id), prov_id
        edge_id = app.neo4j.generate_id("E")
        volume = _get_volume(persona)
        count = _get_txn_count(persona)
        rel_type = "SELLS_TO" if record_type == "customer" else "BUYS_FROM"
        app.neo4j.create_relationship(
            source_id=src, target_id=tgt, rel_type=rel_type,
            properties={"volume": volume, "count": count, "edge_id": edge_id},
        )
        relationship = {
            "edge_id": edge_id, "source_entity_id": src, "target_entity_id": tgt,
            "rel_type": rel_type, "transaction_volume": volume, "transaction_count": count,
        }

    milvus_result = app.milvus.upsert_golden_record(prov_gr.model_dump())

    if company_id is not None:
        await _invalidate_cache(app, str(company_id))

    elapsed = int((time.time() - start) * 1000)
    return {
        "success": True,
        "provisional_golden_record_id": prov_id,
        "pending_match_id": match_id,
        "golden_record_after": prov_gr.model_dump(),
        "relationship": relationship,
        "sync_status": {"neo4j": True, "mysql_pending": True,
                        "milvus": milvus_result.get("success", False),
                        "redis_invalidated": app.redis.available},
        "duration_ms": elapsed,
    }


# ── Tool 11: merge_golden_records ───────────────────────────

@mcp.tool()
async def merge_golden_records(
    survivor_id: str,
    absorbed_id: str,
    merge_reasoning: dict,
    ctx: Context = None,
) -> dict:
    """Merge two existing golden records (re-evaluation trigger).

    Uses Neo4j multi-statement transaction: upsert survivor, merge edges,
    mark absorbed as MERGED, write audit. Milvus updated accordingly.

    Args:
        survivor_id: Preferred survivor golden record ID.
        absorbed_id: Golden record ID to be absorbed/merged.
        merge_reasoning: Dict with confidence, dimension_scores, reasoning, key_factors.

    Returns:
        Dict with 'success', 'survivor_id', 'absorbed_id', before/after snapshots, sync_status.
    """
    app: AppContext = ctx.request_context.lifespan_context
    start = time.time()

    surv_data = app.neo4j.get_golden_record(survivor_id)
    abso_data = app.neo4j.get_golden_record(absorbed_id)
    if not surv_data or not abso_data:
        return {"success": False, "error": "Golden record not found"}

    survivor = GoldenRecord.model_validate(surv_data)
    absorbed = GoldenRecord.model_validate(abso_data)
    surv_before = dict(surv_data)

    # Survivorship: more sources wins
    if absorbed.source_count > survivor.source_count:
        survivor, absorbed = absorbed, survivor

    all_variants = set(survivor.name_variants) | set(absorbed.name_variants)
    survivor.name_variants = sorted(all_variants)
    survivor.source_records = list(set(survivor.source_records) | set(absorbed.source_records))
    survivor.source_count = len(survivor.source_records)

    s_kw = set(survivor.persona.commodity.top_keywords)
    a_kw = set(absorbed.persona.commodity.top_keywords)
    survivor.persona.commodity.top_keywords = sorted(s_kw | a_kw)

    survivor.confidence = min(0.99, max(survivor.confidence, absorbed.confidence) + 0.05)
    survivor.bucket_keys = generate_bucket_keys(
        survivor.persona, app.config.buckets.max_commodity_keywords)

    audit_dict = {
        "audit_id": f"A-{uuid.uuid4().hex[:8]}",
        "event_id": f"merge-{survivor.golden_record_id}-{absorbed.golden_record_id}",
        "record_id": absorbed.golden_record_id,
        "perspective": "GLOBAL",
        "decision": "MERGE",
        "trigger_type": merge_reasoning.get("trigger", "RE_EVALUATION"),
        "target_golden_id": survivor.golden_record_id,
        "absorbed_golden_id": absorbed.golden_record_id,
        "confidence": merge_reasoning.get("confidence", 0.0),
        "dimension_scores": merge_reasoning.get("dimension_scores", {}),
        "reasoning": merge_reasoning.get("reasoning", ""),
        "key_factors": merge_reasoning.get("key_factors", []),
        "candidates_evaluated": 1,
        "llm_calls": merge_reasoning.get("llm_calls", 0),
        "embedding_calls": merge_reasoning.get("embedding_calls", 0),
        "total_duration_ms": 0,
        "evaluation_chain": [],
        "golden_record_before": surv_before,
        "golden_record_after": survivor.model_dump(),
    }

    # Neo4j multi-statement transaction: upsert survivor + merge edges + audit
    app.neo4j.upsert_entity(survivor.model_dump())
    app.neo4j.merge_entities(survivor.golden_record_id, absorbed.golden_record_id)
    app.neo4j.write_audit(audit_dict)

    milvus_result = app.milvus.upsert_golden_record(survivor.model_dump())
    app.milvus.delete_golden_record(absorbed.golden_record_id)

    await _invalidate_cache(app, survivor.golden_record_id, absorbed.golden_record_id)

    elapsed = int((time.time() - start) * 1000)
    return {
        "success": True,
        "survivor_id": survivor.golden_record_id,
        "absorbed_id": absorbed.golden_record_id,
        "survivor_before": surv_before,
        "survivor_after": survivor.model_dump(),
        "golden_record_after": survivor.model_dump(),
        "audit_record": audit_dict,
        "sync_status": {"neo4j": True, "milvus": milvus_result.get("success", False),
                        "redis_invalidated": app.redis.available},
        "duration_ms": elapsed,
    }


# ── Tool 12: log_decision ───────────────────────────────────

@mcp.tool()
async def log_decision(
    event_id: str,
    record_id: str,
    decision: str,
    target_golden_record_id: str | None,
    confidence: float,
    dimension_scores: dict,
    reasoning: str,
    key_factors: list[str],
    evaluation_chain: list[dict],
    agent_metadata: dict,
    ctx: Context = None,
) -> str:
    """Log an entity resolution decision to the audit trail.

    Every agent invocation should call this to record the decision,
    scores, reasoning, and metadata for compliance and debugging.
    Writes to Neo4j AuditEntry nodes (real-time). Paimon archive
    is written by the classifier orchestrator.

    Args:
        event_id: Unique event ID for this resolution.
        record_id: Record ID being resolved.
        decision: MERGE, NEW_ENTITY, REVIEW, or NO_MERGE_FOUND.
        target_golden_record_id: Golden record ID if MERGE/REVIEW.
        confidence: Confidence score 0.0-1.0.
        dimension_scores: Per-dimension scores dict.
        reasoning: Human-readable reasoning string.
        key_factors: List of key factors that influenced the decision.
        evaluation_chain: List of evaluation step dicts.
        agent_metadata: Additional metadata (trigger_type, candidates_evaluated, etc).

    Returns:
        Audit ID string.
    """
    app: AppContext = ctx.request_context.lifespan_context

    audit_dict = {
        "audit_id": f"A-{uuid.uuid4().hex[:8]}",
        "event_id": event_id,
        "record_id": record_id,
        "perspective": "GLOBAL",
        "decision": decision,
        "trigger_type": agent_metadata.get("trigger_type", "AI_AGENT"),
        "target_golden_id": target_golden_record_id,
        "confidence": confidence,
        "dimension_scores": dimension_scores,
        "reasoning": reasoning,
        "key_factors": key_factors,
        "candidates_evaluated": agent_metadata.get("candidates_evaluated", 0),
        "llm_calls": agent_metadata.get("llm_calls", 0),
        "embedding_calls": agent_metadata.get("embedding_calls", 0),
        "total_duration_ms": agent_metadata.get("total_duration_ms", 0),
        "evaluation_chain": evaluation_chain,
    }
    return app.neo4j.write_audit(audit_dict)
