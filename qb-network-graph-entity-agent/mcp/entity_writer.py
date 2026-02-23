"""
MCP Server 3: entity_writer — All write-side operations.

5 tools:
  merge_into_golden_record   — merge orphan into existing GR
  create_golden_record       — create new GR from orphan
  submit_for_review          — submit ambiguous match to human queue
  merge_golden_records       — merge two existing GRs (re-evaluation)
  log_decision               — audit every invocation

Write path per golden record mutation:
  1. MySQL COMMIT   (source of truth, ACID)              ~5ms
  2. Milvus UPSERT  (vector search, immediate Pattern A) ~150ms
  3. KG triples     (ontology links, if available)       ~30ms

Design doc §2.3.
"""
from __future__ import annotations
import logging
import time
import uuid

from models.persona import GoldenRecord, ClassifiedPersona
from models.audit import AuditRecord, PendingResolution
from clients.mysql_client import MySQLClient
from clients.milvus_client import MilvusClient
from mcp.knowledge_graph import KnowledgeGraphServer
from utils.bucket_keys import generate_bucket_keys
from config import AgentConfig

logger = logging.getLogger(__name__)


class EntityWriter:
    """MCP Server 3 — all mutations + audit.

    v3: MySQL + Milvus. No Redis in write path.
    """

    def __init__(
        self,
        config: AgentConfig,
        mysql: MySQLClient,
        milvus: MilvusClient | None = None,
        knowledge_graph: KnowledgeGraphServer | None = None,
    ):
        self._cfg = config
        self._mysql = mysql
        self._milvus = milvus
        self._kg = knowledge_graph

    def set_knowledge_graph(self, kg: KnowledgeGraphServer):
        self._kg = kg

    def set_milvus(self, milvus: MilvusClient):
        self._milvus = milvus

    # ── Tool 1: merge_into_golden_record ────────────────────

    def merge_into_golden_record(
        self,
        orphan_record_id: str,
        orphan_persona: ClassifiedPersona,
        golden_record_id: str,
        merge_reasoning: dict,
    ) -> dict:
        """Merge orphan into existing golden record."""
        start = time.time()

        gr_data = self._mysql.get_golden_record(golden_record_id)
        if not gr_data:
            return {"success": False, "error": f"Golden record {golden_record_id} not found"}

        before_snapshot = dict(gr_data)
        gr = GoldenRecord.model_validate(gr_data)
        _apply_survivorship(gr, orphan_persona)

        orphan_name = orphan_persona.identity.normalized_name
        if orphan_name and orphan_name.upper() not in {v.upper() for v in gr.name_variants}:
            gr.name_variants.append(orphan_name)

        gr.source_count += 1
        gr.source_records.append(orphan_record_id)
        gr.bucket_keys = generate_bucket_keys(gr.persona, self._cfg.buckets.max_commodity_keywords)
        gr.confidence = min(0.99, gr.confidence + 0.05)

        # 1. MySQL
        self._mysql.write_golden_record(gr)

        # 2. Milvus
        milvus_result = {}
        if self._milvus:
            milvus_result = self._milvus.upsert_golden_record(gr.model_dump())

        # 3. KG
        kg_result = {}
        if self._kg:
            kg_result = self._kg.write_entity_triples(
                gr.golden_record_id, _gr_to_kg_attrs(gr, orphan_persona))

        elapsed = int((time.time() - start) * 1000)
        return {
            "success": True,
            "golden_record_id": gr.golden_record_id,
            "golden_record_before": before_snapshot,
            "golden_record_after": gr.model_dump(),
            "sync_status": {"mysql": True, "milvus": milvus_result.get("success", False),
                            "kg_store": kg_result.get("success", False)},
            "duration_ms": elapsed,
        }

    # ── Tool 2: create_golden_record ────────────────────────

    def create_golden_record(
        self,
        orphan_record_id: str,
        orphan_persona: ClassifiedPersona,
        creation_reasoning: dict,
    ) -> dict:
        """Create a new golden record from unmatched orphan."""
        start = time.time()
        gr_id = self._mysql.generate_id("G")
        name = _resolve_canonical_name(orphan_persona)

        gr = GoldenRecord(
            golden_record_id=gr_id,
            canonical_name=name,
            name_variants=[name] if name else [],
            persona=orphan_persona,
            source_count=1,
            confidence=0.5,
            status="ACTIVE",
            entity_type="PHANTOM",
            source_records=[orphan_record_id],
            bucket_keys=generate_bucket_keys(
                orphan_persona, self._cfg.buckets.max_commodity_keywords),
        )

        self._mysql.write_golden_record(gr)

        milvus_result = {}
        if self._milvus:
            milvus_result = self._milvus.upsert_golden_record(gr.model_dump())

        kg_result = {}
        if self._kg:
            kg_result = self._kg.write_entity_triples(
                gr.golden_record_id, _gr_to_kg_attrs(gr, orphan_persona))

        elapsed = int((time.time() - start) * 1000)
        return {
            "success": True,
            "golden_record_id": gr_id,
            "bucket_keys": gr.bucket_keys,
            "sync_status": {"mysql": True, "milvus": milvus_result.get("success", False),
                            "kg_store": kg_result.get("success", False)},
            "duration_ms": elapsed,
        }

    # ── Tool 3: submit_for_review ───────────────────────────

    def submit_for_review(
        self,
        orphan_record_id: str,
        orphan_persona: ClassifiedPersona,
        candidate_golden_record_id: str,
        review_reasoning: dict,
    ) -> dict:
        """Submit ambiguous match to human review queue."""
        start = time.time()

        prov_id = self._mysql.generate_id("G")
        name = _resolve_canonical_name(orphan_persona)
        prov_gr = GoldenRecord(
            golden_record_id=prov_id,
            canonical_name=name,
            name_variants=[name] if name else [],
            persona=orphan_persona,
            source_count=1,
            confidence=review_reasoning.get("confidence", 0.5),
            status="PROVISIONAL",
            entity_type="PHANTOM",
            source_records=[orphan_record_id],
            bucket_keys=generate_bucket_keys(
                orphan_persona, self._cfg.buckets.max_commodity_keywords),
        )

        match_id = f"PR-{uuid.uuid4().hex[:8]}"
        pending = PendingResolution(
            match_id=match_id,
            orphan_golden_id=prov_id,
            candidate_golden_id=candidate_golden_record_id,
            confidence=review_reasoning.get("confidence", 0.5),
            dimension_scores=review_reasoning.get("dimension_scores", {}),
            reasoning=review_reasoning.get("reasoning", ""),
            key_uncertainty=review_reasoning.get("key_uncertainty", ""),
        )

        # Single transaction: insert provisional GR + pending resolution together
        # to avoid FK violation on separate connections
        self._mysql.write_golden_record_and_pending(prov_gr, pending)

        milvus_result = {}
        if self._milvus:
            milvus_result = self._milvus.upsert_golden_record(prov_gr.model_dump())

        elapsed = int((time.time() - start) * 1000)
        return {
            "success": True,
            "provisional_golden_record_id": prov_id,
            "pending_match_id": match_id,
            "sync_status": {"mysql": True, "milvus": milvus_result.get("success", False)},
            "duration_ms": elapsed,
        }

    # ── Tool 4: merge_golden_records ────────────────────────

    def merge_golden_records(
        self,
        survivor_id: str,
        absorbed_id: str,
        merge_reasoning: dict,
    ) -> dict:
        """Merge two existing golden records (re-evaluation trigger).

        Uses MySQL transactional_merge — single COMMIT for all three writes.
        """
        start = time.time()

        surv_data = self._mysql.get_golden_record(survivor_id)
        abso_data = self._mysql.get_golden_record(absorbed_id)
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
            survivor.persona, self._cfg.buckets.max_commodity_keywords)

        audit = AuditRecord(
            audit_id=f"A-{uuid.uuid4().hex[:8]}",
            event_id=f"merge-{survivor.golden_record_id}-{absorbed.golden_record_id}",
            record_id=absorbed.golden_record_id,
            perspective="GLOBAL",
            decision="MERGE",
            trigger_type=merge_reasoning.get("trigger", "RE_EVALUATION"),
            target_golden_id=survivor.golden_record_id,
            confidence=merge_reasoning.get("confidence", 0.0),
            dimension_scores=merge_reasoning.get("dimension_scores", {}),
            reasoning=merge_reasoning.get("reasoning", ""),
            key_factors=merge_reasoning.get("key_factors", []),
            candidates_evaluated=1,
            llm_calls=merge_reasoning.get("llm_calls", 0),
            embedding_calls=merge_reasoning.get("embedding_calls", 0),
            total_duration_ms=0,
            evaluation_chain=[],
        )

        # ═══ TRANSACTIONAL MERGE ═══
        success = self._mysql.transactional_merge(
            survivor=survivor, absorbed_id=absorbed.golden_record_id, audit=audit)

        if not success:
            return {"success": False, "error": "MySQL transaction failed — rolled back"}

        # Milvus: recompute survivor + delete absorbed
        milvus_result = {}
        if self._milvus:
            milvus_result = self._milvus.upsert_golden_record(survivor.model_dump())
            self._milvus.delete_golden_record(absorbed.golden_record_id)

        # KG: merge redirect
        kg_result = {}
        if self._kg:
            new_variants = list(set(absorbed.name_variants) - set(surv_data.get("name_variants", [])))
            new_unspscs = list(set(absorbed.persona.commodity.top_keywords) - s_kw)
            kg_result = self._kg.write_merge_redirect(
                survivor.golden_record_id, absorbed.golden_record_id,
                {"name_variants": new_variants, "unspsc_codes": new_unspscs})

        elapsed = int((time.time() - start) * 1000)
        return {
            "success": True,
            "survivor_id": survivor.golden_record_id,
            "absorbed_id": absorbed.golden_record_id,
            "survivor_before": surv_before,
            "survivor_after": survivor.model_dump(),
            "sync_status": {"mysql": True, "milvus": milvus_result.get("success", False),
                            "kg_store": kg_result.get("success", False)},
            "duration_ms": elapsed,
        }

    # ── Tool 5: log_decision ────────────────────────────────

    def log_decision(
        self,
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
    ) -> str:
        audit = AuditRecord(
            audit_id=f"A-{uuid.uuid4().hex[:8]}",
            event_id=event_id,
            record_id=record_id,
            perspective="GLOBAL",
            decision=decision,
            trigger_type=agent_metadata.get("trigger_type", "AI_AGENT"),
            target_golden_id=target_golden_record_id,
            confidence=confidence,
            dimension_scores=dimension_scores,
            reasoning=reasoning,
            key_factors=key_factors,
            candidates_evaluated=agent_metadata.get("candidates_evaluated", 0),
            llm_calls=agent_metadata.get("llm_calls", 0),
            embedding_calls=agent_metadata.get("embedding_calls", 0),
            total_duration_ms=agent_metadata.get("total_duration_ms", 0),
            evaluation_chain=evaluation_chain,
        )
        return self._mysql.write_audit(audit)


# ── Helpers ─────────────────────────────────────────────────

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
    """Resolve the best canonical name from persona fields.

    Fallback chain: normalized_name → canonical_name (alias) → name_first_token.
    """
    name = persona.identity.normalized_name
    if not name:
        name = getattr(persona.identity, 'canonical_name', '') or ''
    if not name and persona.identity.name_first_token:
        name = persona.identity.name_first_token
    return name


def _gr_to_kg_attrs(gr: GoldenRecord, orphan: ClassifiedPersona) -> dict:
    # Ensure canonical_name is never empty in KG triples
    name = gr.canonical_name
    if not name:
        name = _resolve_canonical_name(orphan)
    if not name and gr.name_variants:
        name = gr.name_variants[0]

    return {
        "canonical_name": name,
        "entity_type": gr.entity_type,
        "confidence": gr.confidence,
        "naics_codes": [gr.persona.industry.naics_code] if gr.persona.industry.naics_code else [],
        "unspsc_codes": [],
        "geo_location": (gr.persona.location.city_norm or "").lower(),
        "name_variants": gr.name_variants,
        "ein": gr.persona.identity.ein_clean or "",
        "email": gr.persona.identity.email or "",
        "phone": gr.persona.identity.phone_digits or "",
    }
