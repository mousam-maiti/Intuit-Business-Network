"""
MySQL client — golden record source of truth.

Replaces both PaimonClient (golden record writes) and RedisClient (bucket index reads).

Key insight: The Redis bucket_index pattern (ZADD bucket:{key} → ZREVRANGE) maps directly
to MySQL indexed queries on golden_records. At 1M records and 39 QPS, these indexed
lookups are sub-10ms — no caching layer needed.

Bucket key → MySQL index mapping:
  ein:{value}           → WHERE ein = ?              → idx_gr_ein (unique)
  name:{token}+{state}  → WHERE canonical_name LIKE ? AND state = ? → ft_gr_name + idx_gr_state
  naics4:{code}+{state} → WHERE naics_code LIKE ? AND state = ?     → idx_gr_naics_state
  zip3:{value}          → WHERE zip3 = ?              → idx_gr_zip3
  city:{city}+{state}   → WHERE city = ? AND state = ? → idx_gr_city_state
  phone:{digits}        → WHERE phone_digits = ?      → (needs index — add if needed)

Transactional merge: survivor UPDATE + absorbed MERGED + audit INSERT in one COMMIT.
"""
from __future__ import annotations
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Optional

from config import MySQLConfig
from models.persona import GoldenRecord, ClassifiedPersona
from models.audit import AuditRecord, PendingResolution

logger = logging.getLogger(__name__)

try:
    import mysql.connector
    from mysql.connector import pooling
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False


class MySQLClient:
    """MySQL client for golden record CRUD + bucket-key lookups.

    Replaces RedisClient (bucket index) + PaimonClient (golden record store).
    Falls back to in-memory dict if no MySQL driver available.
    """

    def __init__(self, cfg: MySQLConfig):
        self._cfg = cfg
        self._pool = None
        self._using_mock = False

        # In-memory fallback
        self._mock_golden: dict[str, dict] = {}
        self._mock_audit: list[dict] = []
        self._mock_pending: list[dict] = []
        self._mock_relationships: dict[str, dict] = {}

    async def connect(self):
        """Initialize connection pool."""
        if not HAS_MYSQL:
            logger.warning("No MySQL driver — using in-memory fallback "
                           "(pip install mysql-connector-python)")
            self._using_mock = True
            return

        try:
            self._pool = pooling.MySQLConnectionPool(
                pool_name="agent_pool",
                pool_size=self._cfg.pool_size,
                host=self._cfg.host,
                port=self._cfg.port,
                user=self._cfg.user,
                password=self._cfg.password,
                database=self._cfg.database,
                autocommit=False,
            )
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
            logger.info(f"MySQL connected: {self._cfg.host}:{self._cfg.port}/{self._cfg.database}")
        except Exception as e:
            logger.warning(f"MySQL connection failed ({e}) — using in-memory fallback")
            self._using_mock = True

    @contextmanager
    def _get_conn(self):
        """Get connection from pool with auto-release."""
        conn = self._pool.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    # ═══════════════════════════════════════════════════════════
    # GOLDEN RECORD READS
    # ═══════════════════════════════════════════════════════════

    def get_golden_record(self, golden_record_id: str) -> Optional[dict]:
        """Point read by PK — sub-1ms."""
        if self._using_mock:
            return self._mock_golden.get(golden_record_id)

        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM golden_records WHERE golden_record_id = %s",
                (golden_record_id,)
            )
            row = cursor.fetchone()
            return self._deserialize_gr(row) if row else None

    def get_all_golden_records(self, active_only: bool = True) -> list[dict]:
        """Read all golden records (for backfill/cold start)."""
        if self._using_mock:
            records = list(self._mock_golden.values())
            if active_only:
                records = [r for r in records if r.get("status") in ("ACTIVE", "PROVISIONAL")]
            return records

        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            if active_only:
                cursor.execute("SELECT * FROM golden_records WHERE status IN ('ACTIVE', 'PROVISIONAL')")
            else:
                cursor.execute("SELECT * FROM golden_records")
            return [self._deserialize_gr(r) for r in cursor.fetchall()]

    # ═══════════════════════════════════════════════════════════
    # BUCKET-KEY LOOKUPS (replaces Redis sorted sets)
    # ═══════════════════════════════════════════════════════════

    def find_by_bucket_key(self, bucket_key: str) -> list[str]:
        """Translate a bucket key into a MySQL indexed query.

        Returns list of golden_record_ids matching the bucket key.
        This is the direct replacement for Redis ZREVRANGE bucket:{key}.

        Bucket key format examples:
          ein:743218976
          name:BOBS+TX
          naics4:4237+TX
          zip3:787
          city:AUSTIN+TX
          phone:5125551234
        """
        if self._using_mock:
            return self._find_mock_bucket(bucket_key)

        parts = bucket_key.split(":", 1)
        if len(parts) != 2:
            return []

        prefix, value = parts[0], parts[1]

        with self._get_conn() as conn:
            cursor = conn.cursor()

            if prefix == "ein":
                cursor.execute(
                    "SELECT golden_record_id FROM golden_records "
                    "WHERE ein = %s AND status != 'MERGED'",
                    (value,)
                )

            elif prefix == "name":
                # name:BOBS+TX → FULLTEXT match on name + state filter
                name_state = value.split("+", 1)
                if len(name_state) == 2:
                    name_token, state = name_state
                    # FULLTEXT for name, indexed filter for state
                    cursor.execute(
                        "SELECT golden_record_id FROM golden_records "
                        "WHERE MATCH(canonical_name) AGAINST(%s IN BOOLEAN MODE) "
                        "AND state = %s AND status != 'MERGED'",
                        (f"{name_token}*", state)
                    )
                else:
                    cursor.execute(
                        "SELECT golden_record_id FROM golden_records "
                        "WHERE MATCH(canonical_name) AGAINST(%s IN BOOLEAN MODE) "
                        "AND status != 'MERGED'",
                        (f"{value}*",)
                    )

            elif prefix == "naics4":
                # naics4:4237+TX → NAICS prefix + state
                naics_state = value.split("+", 1)
                if len(naics_state) == 2:
                    naics_prefix, state = naics_state
                    cursor.execute(
                        "SELECT golden_record_id FROM golden_records "
                        "WHERE naics_code LIKE %s AND state = %s AND status != 'MERGED'",
                        (f"{naics_prefix}%", state)
                    )
                else:
                    cursor.execute(
                        "SELECT golden_record_id FROM golden_records "
                        "WHERE naics_code LIKE %s AND status != 'MERGED'",
                        (f"{value}%",)
                    )

            elif prefix == "zip3":
                cursor.execute(
                    "SELECT golden_record_id FROM golden_records "
                    "WHERE zip3 = %s AND status != 'MERGED'",
                    (value,)
                )

            elif prefix == "city":
                # city:AUSTIN+TX
                city_state = value.split("+", 1)
                if len(city_state) == 2:
                    city, state = city_state
                    cursor.execute(
                        "SELECT golden_record_id FROM golden_records "
                        "WHERE city = %s AND state = %s AND status != 'MERGED'",
                        (city, state)
                    )
                else:
                    cursor.execute(
                        "SELECT golden_record_id FROM golden_records "
                        "WHERE city = %s AND status != 'MERGED'",
                        (value,)
                    )

            elif prefix == "phone":
                cursor.execute(
                    "SELECT golden_record_id FROM golden_records "
                    "WHERE phone_digits = %s AND status != 'MERGED'",
                    (value,)
                )

            elif prefix == "email_domain":
                # email_domain:bobsplumbing.com → match email domain
                cursor.execute(
                    "SELECT golden_record_id FROM golden_records "
                    "WHERE email LIKE %s AND status != 'MERGED'",
                    (f"%@{value}",)
                )

            elif prefix == "naics3":
                # naics3:238+TX → NAICS 3-digit subsector + state
                naics_state = value.split("+", 1)
                if len(naics_state) == 2:
                    naics_prefix, state = naics_state
                    cursor.execute(
                        "SELECT golden_record_id FROM golden_records "
                        "WHERE naics_subsector = %s AND state = %s AND status != 'MERGED'",
                        (naics_prefix, state)
                    )
                else:
                    cursor.execute(
                        "SELECT golden_record_id FROM golden_records "
                        "WHERE naics_subsector = %s AND status != 'MERGED'",
                        (value,)
                    )

            elif prefix == "commodity":
                # commodity:pvc pipe+TX → keyword search in commodity_keywords JSON + state
                kw_state = value.split("+", 1)
                if len(kw_state) == 2:
                    keyword, state = kw_state
                    cursor.execute(
                        "SELECT golden_record_id FROM golden_records "
                        "WHERE commodity_keywords LIKE %s AND state = %s AND status != 'MERGED'",
                        (f"%{keyword}%", state)
                    )
                else:
                    cursor.execute(
                        "SELECT golden_record_id FROM golden_records "
                        "WHERE commodity_keywords LIKE %s AND status != 'MERGED'",
                        (f"%{value}%",)
                    )

            else:
                logger.warning(f"Unknown bucket key prefix: {prefix}")
                return []

            return [row[0] for row in cursor.fetchall()]

    def _find_mock_bucket(self, bucket_key: str) -> list[str]:
        """In-memory bucket search for development."""
        parts = bucket_key.split(":", 1)
        if len(parts) != 2:
            return []
        prefix, value = parts

        results = []
        for gr_id, gr in self._mock_golden.items():
            if gr.get("status") == "MERGED":
                continue
            bk_list = gr.get("bucket_keys", [])
            if isinstance(bk_list, str):
                try:
                    bk_list = json.loads(bk_list)
                except (json.JSONDecodeError, TypeError):
                    bk_list = []
            if bucket_key in bk_list:
                results.append(gr_id)
        return results

    # ═══════════════════════════════════════════════════════════
    # GOLDEN RECORD WRITES
    # ═══════════════════════════════════════════════════════════

    def write_golden_record(self, gr):
        """Upsert a golden record (INSERT ON DUPLICATE KEY UPDATE).

        Accepts a GoldenRecord instance or a dict (auto-coerced).
        """
        if isinstance(gr, dict):
            gr = GoldenRecord.model_validate(gr)
        now = datetime.now(timezone.utc).isoformat()
        data = self._serialize_gr(gr, now)

        if self._using_mock:
            self._mock_golden[gr.golden_record_id] = {
                **gr.model_dump(),
                "updated_at": now,
                **{k: data[k] for k in ["ein", "phone_digits", "naics_code",
                   "naics_sector", "naics_subsector", "state", "city", "zip5", "zip3"]},
            }
            return

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO golden_records (
                    golden_record_id, canonical_name, name_variants,
                    ein, phone_digits, email, contact_name,
                    naics_code, naics_sector, naics_subsector,
                    state, city, zip5, zip3, street_address,
                    commodity_keywords, service_categories,
                    total_volume, avg_transaction, transaction_count, volume_bracket,
                    source_count, source_records, confidence, status, merged_into,
                    entity_type, persona, bucket_keys, created_at, updated_at
                ) VALUES (
                    %(golden_record_id)s, %(canonical_name)s, %(name_variants)s,
                    %(ein)s, %(phone_digits)s, %(email)s, %(contact_name)s,
                    %(naics_code)s, %(naics_sector)s, %(naics_subsector)s,
                    %(state)s, %(city)s, %(zip5)s, %(zip3)s, %(street_address)s,
                    %(commodity_keywords)s, %(service_categories)s,
                    %(total_volume)s, %(avg_transaction)s, %(transaction_count)s, %(volume_bracket)s,
                    %(source_count)s, %(source_records)s, %(confidence)s, %(status)s, %(merged_into)s,
                    %(entity_type)s, %(persona)s, %(bucket_keys)s, %(created_at)s, %(updated_at)s
                ) ON DUPLICATE KEY UPDATE
                    canonical_name = VALUES(canonical_name),
                    name_variants = VALUES(name_variants),
                    ein = VALUES(ein), phone_digits = VALUES(phone_digits),
                    email = VALUES(email), contact_name = VALUES(contact_name),
                    naics_code = VALUES(naics_code), naics_sector = VALUES(naics_sector),
                    naics_subsector = VALUES(naics_subsector),
                    state = VALUES(state), city = VALUES(city),
                    zip5 = VALUES(zip5), zip3 = VALUES(zip3),
                    street_address = VALUES(street_address),
                    commodity_keywords = VALUES(commodity_keywords),
                    service_categories = VALUES(service_categories),
                    total_volume = VALUES(total_volume),
                    avg_transaction = VALUES(avg_transaction),
                    transaction_count = VALUES(transaction_count),
                    volume_bracket = VALUES(volume_bracket),
                    source_count = VALUES(source_count),
                    source_records = VALUES(source_records),
                    confidence = VALUES(confidence),
                    status = VALUES(status),
                    merged_into = VALUES(merged_into),
                    entity_type = VALUES(entity_type),
                    persona = VALUES(persona),
                    bucket_keys = VALUES(bucket_keys),
                    updated_at = VALUES(updated_at)
            """, data)
            conn.commit()

    # ═══════════════════════════════════════════════════════════
    # TRANSACTIONAL MERGE
    # ═══════════════════════════════════════════════════════════

    def transactional_merge(
        self,
        survivor: GoldenRecord,
        absorbed_id: str,
        audit: AuditRecord,
    ) -> bool:
        """Atomically: update survivor + mark absorbed MERGED + write audit.

        Single MySQL transaction. Either all succeed or none.
        """
        now = datetime.now(timezone.utc).isoformat()

        if self._using_mock:
            self._mock_golden[survivor.golden_record_id] = {
                **survivor.model_dump(), "updated_at": now,
            }
            if absorbed_id in self._mock_golden:
                self._mock_golden[absorbed_id]["status"] = "MERGED"
                self._mock_golden[absorbed_id]["merged_into"] = survivor.golden_record_id
            self._mock_audit.append(audit.model_dump())
            return True

        with self._get_conn() as conn:
            try:
                cursor = conn.cursor()

                # 1. Update survivor
                surv_data = self._serialize_gr(survivor, now)
                cursor.execute("""
                    UPDATE golden_records SET
                        canonical_name=%(canonical_name)s, name_variants=%(name_variants)s,
                        ein=%(ein)s, phone_digits=%(phone_digits)s,
                        email=%(email)s, contact_name=%(contact_name)s,
                        naics_code=%(naics_code)s, naics_sector=%(naics_sector)s,
                        naics_subsector=%(naics_subsector)s,
                        state=%(state)s, city=%(city)s, zip5=%(zip5)s, zip3=%(zip3)s,
                        street_address=%(street_address)s,
                        commodity_keywords=%(commodity_keywords)s,
                        service_categories=%(service_categories)s,
                        total_volume=%(total_volume)s, avg_transaction=%(avg_transaction)s,
                        transaction_count=%(transaction_count)s, volume_bracket=%(volume_bracket)s,
                        source_count=%(source_count)s, source_records=%(source_records)s,
                        confidence=%(confidence)s,
                        persona=%(persona)s, bucket_keys=%(bucket_keys)s,
                        updated_at=%(updated_at)s
                    WHERE golden_record_id=%(golden_record_id)s
                """, surv_data)

                # 2. Mark absorbed as MERGED
                cursor.execute("""
                    UPDATE golden_records SET status='MERGED', merged_into=%s, updated_at=%s
                    WHERE golden_record_id=%s
                """, (survivor.golden_record_id, now, absorbed_id))

                # 3. Write audit
                audit_data = self._serialize_audit(audit, now)
                cursor.execute("""
                    INSERT INTO resolution_audit (
                        audit_id, event_id, record_id, perspective, decision,
                        trigger_type, target_golden_id, absorbed_golden_id,
                        confidence, dimension_scores, reasoning, key_factors,
                        candidates_evaluated, llm_calls, embedding_calls,
                        total_duration_ms, evaluation_chain,
                        golden_record_before, golden_record_after, created_at
                    ) VALUES (
                        %(audit_id)s, %(event_id)s, %(record_id)s, %(perspective)s, %(decision)s,
                        %(trigger_type)s, %(target_golden_id)s, %(absorbed_golden_id)s,
                        %(confidence)s, %(dimension_scores)s, %(reasoning)s, %(key_factors)s,
                        %(candidates_evaluated)s, %(llm_calls)s, %(embedding_calls)s,
                        %(total_duration_ms)s, %(evaluation_chain)s,
                        %(golden_record_before)s, %(golden_record_after)s, %(created_at)s
                    )
                """, audit_data)

                conn.commit()
                logger.info(f"Transactional merge: {absorbed_id} → {survivor.golden_record_id}")
                return True

            except Exception as e:
                conn.rollback()
                logger.error(f"Merge transaction ROLLED BACK: {e}")
                return False

    # ═══════════════════════════════════════════════════════════
    # STANDALONE WRITES
    # ═══════════════════════════════════════════════════════════

    def mark_merged(self, absorbed_id: str, survivor_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        if self._using_mock:
            if absorbed_id in self._mock_golden:
                self._mock_golden[absorbed_id]["status"] = "MERGED"
                self._mock_golden[absorbed_id]["merged_into"] = survivor_id
            return True
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE golden_records SET status='MERGED', merged_into=%s, updated_at=%s "
                "WHERE golden_record_id=%s",
                (survivor_id, now, absorbed_id)
            )
            conn.commit()
            return True

    def write_audit(self, audit: AuditRecord) -> str:
        now = datetime.now(timezone.utc).isoformat()
        if self._using_mock:
            self._mock_audit.append(audit.model_dump())
            return audit.audit_id
        data = self._serialize_audit(audit, now)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO resolution_audit (
                    audit_id, event_id, record_id, perspective, decision,
                    trigger_type, target_golden_id, absorbed_golden_id,
                    confidence, dimension_scores, reasoning, key_factors,
                    candidates_evaluated, llm_calls, embedding_calls,
                    total_duration_ms, evaluation_chain,
                    golden_record_before, golden_record_after, created_at
                ) VALUES (
                    %(audit_id)s, %(event_id)s, %(record_id)s, %(perspective)s, %(decision)s,
                    %(trigger_type)s, %(target_golden_id)s, %(absorbed_golden_id)s,
                    %(confidence)s, %(dimension_scores)s, %(reasoning)s, %(key_factors)s,
                    %(candidates_evaluated)s, %(llm_calls)s, %(embedding_calls)s,
                    %(total_duration_ms)s, %(evaluation_chain)s,
                    %(golden_record_before)s, %(golden_record_after)s, %(created_at)s
                )
            """, data)
            conn.commit()
        return audit.audit_id

    def write_pending_resolution(self, pending: PendingResolution) -> str:
        if self._using_mock:
            self._mock_pending.append(pending.model_dump())
            return pending.match_id
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO pending_resolution (
                    match_id, orphan_golden_id, candidate_golden_id,
                    confidence, dimension_scores, reasoning, key_uncertainty,
                    status, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING', CURRENT_TIMESTAMP(3))
            """, (
                pending.match_id, pending.orphan_golden_id,
                pending.candidate_golden_id, pending.confidence,
                json.dumps(pending.dimension_scores, default=str),
                pending.reasoning, pending.key_uncertainty,
            ))
            conn.commit()
        return pending.match_id

    def write_golden_record_and_pending(
        self, gr, pending: PendingResolution,
    ) -> str:
        """Insert provisional golden record + pending resolution in one transaction.

        Avoids FK violation where pending_resolution.orphan_golden_id references
        a golden_record that isn't visible yet on a different connection.
        """
        if isinstance(gr, dict):
            gr = GoldenRecord.model_validate(gr)
        now = datetime.now(timezone.utc).isoformat()
        data = self._serialize_gr(gr, now)

        if self._using_mock:
            self._mock_golden[gr.golden_record_id] = {
                **gr.model_dump(), "updated_at": now,
                **{k: data[k] for k in ["ein", "phone_digits", "naics_code",
                   "naics_sector", "naics_subsector", "state", "city", "zip5", "zip3"]},
            }
            self._mock_pending.append(pending.model_dump())
            return pending.match_id

        with self._get_conn() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO golden_records (
                        golden_record_id, canonical_name, name_variants,
                        ein, phone_digits, email, contact_name,
                        naics_code, naics_sector, naics_subsector,
                        state, city, zip5, zip3, street_address,
                        commodity_keywords, service_categories,
                        total_volume, avg_transaction, transaction_count, volume_bracket,
                        source_count, source_records, confidence, status, merged_into,
                        entity_type, persona, bucket_keys, created_at, updated_at
                    ) VALUES (
                        %(golden_record_id)s, %(canonical_name)s, %(name_variants)s,
                        %(ein)s, %(phone_digits)s, %(email)s, %(contact_name)s,
                        %(naics_code)s, %(naics_sector)s, %(naics_subsector)s,
                        %(state)s, %(city)s, %(zip5)s, %(zip3)s, %(street_address)s,
                        %(commodity_keywords)s, %(service_categories)s,
                        %(total_volume)s, %(avg_transaction)s, %(transaction_count)s, %(volume_bracket)s,
                        %(source_count)s, %(source_records)s, %(confidence)s, %(status)s, %(merged_into)s,
                        %(entity_type)s, %(persona)s, %(bucket_keys)s, %(created_at)s, %(updated_at)s
                    ) ON DUPLICATE KEY UPDATE
                        canonical_name = VALUES(canonical_name),
                        name_variants = VALUES(name_variants),
                        confidence = VALUES(confidence),
                        status = VALUES(status),
                        persona = VALUES(persona),
                        bucket_keys = VALUES(bucket_keys),
                        updated_at = VALUES(updated_at)
                """, data)
                gr_rows = cursor.rowcount
                logger.debug(f"GR insert rowcount={gr_rows} id={data['golden_record_id']} "
                             f"orphan={pending.orphan_golden_id} candidate={pending.candidate_golden_id}")
                cursor.execute("""
                    INSERT INTO pending_resolution (
                        match_id, orphan_golden_id, candidate_golden_id,
                        confidence, dimension_scores, reasoning, key_uncertainty,
                        status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING', CURRENT_TIMESTAMP(3))
                """, (
                    pending.match_id, pending.orphan_golden_id,
                    pending.candidate_golden_id, pending.confidence,
                    json.dumps(pending.dimension_scores, default=str),
                    pending.reasoning, pending.key_uncertainty,
                ))
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"write_golden_record_and_pending FAILED: gr_id={data['golden_record_id']} "
                             f"orphan={pending.orphan_golden_id} candidate={pending.candidate_golden_id} err={e}")
                raise
        return pending.match_id

    def write_relationship(self, edge_id: str, source_id: str, target_id: str,
                           volume: float = None, count: int = None,
                           first_txn: str = None, last_txn: str = None):
        if self._using_mock:
            self._mock_relationships[edge_id] = {
                "edge_id": edge_id, "source_entity_id": source_id,
                "target_entity_id": target_id, "transaction_volume": volume,
            }
            return
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO relationships (
                    edge_id, source_entity_id, target_entity_id,
                    transaction_volume, transaction_count,
                    first_transaction, last_transaction
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    transaction_volume=VALUES(transaction_volume),
                    transaction_count=VALUES(transaction_count),
                    last_transaction=VALUES(last_transaction),
                    updated_at=CURRENT_TIMESTAMP(3)
            """, (edge_id, source_id, target_id, volume, count, first_txn, last_txn))
            conn.commit()

    # ═══════════════════════════════════════════════════════════
    # LIFECYCLE
    # ═══════════════════════════════════════════════════════════

    def generate_id(self, prefix: str = "G") -> str:
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    async def close(self):
        if self._pool:
            logger.info("MySQL connection pool released")

    @property
    def record_count(self) -> int:
        if self._using_mock:
            return len(self._mock_golden)
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM golden_records WHERE status != 'MERGED'")
                return cursor.fetchone()[0]
        except Exception:
            return len(self._mock_golden)

    @property
    def using_mock(self) -> bool:
        return self._using_mock

    # ═══════════════════════════════════════════════════════════
    # SERIALIZATION
    # ═══════════════════════════════════════════════════════════

    def _serialize_gr(self, gr: GoldenRecord, now: str) -> dict:
        p = gr.persona
        return {
            "golden_record_id": gr.golden_record_id,
            "canonical_name": gr.canonical_name,
            "name_variants": json.dumps(gr.name_variants),
            "ein": p.identity.ein_clean if p else None,
            "phone_digits": p.identity.phone_digits if p else None,
            "email": p.identity.email if p else None,
            "contact_name": None,
            "naics_code": p.industry.naics_code if p else None,
            "naics_sector": p.industry.naics_sector if p else None,
            "naics_subsector": p.industry.naics_subsector if p else None,
            "state": p.location.state if p else None,
            "city": p.location.city_norm if p else None,
            "zip5": p.location.zip5 if p else None,
            "zip3": p.location.zip3 if p else None,
            "street_address": None,
            "commodity_keywords": json.dumps(p.commodity.top_keywords) if p else "[]",
            "service_categories": json.dumps(p.commodity.service_categories) if p else "[]",
            "total_volume": (p.behavioral.avg_transaction * p.behavioral.transaction_count
                if p and p.behavioral.avg_transaction and p.behavioral.transaction_count else None),
            "avg_transaction": p.behavioral.avg_transaction if p else None,
            "transaction_count": p.behavioral.transaction_count if p else None,
            "volume_bracket": p.behavioral.volume_bracket if p else None,
            "source_count": gr.source_count,
            "source_records": json.dumps(gr.source_records),
            "confidence": gr.confidence,
            "status": gr.status,
            "merged_into": gr.merged_into,
            "entity_type": gr.entity_type,
            "persona": json.dumps(gr.persona.model_dump() if hasattr(gr.persona, 'model_dump') else gr.persona, default=str),
            "bucket_keys": json.dumps(gr.bucket_keys),
            "created_at": now,
            "updated_at": now,
        }

    def _serialize_audit(self, audit: AuditRecord, now: str) -> dict:
        return {
            "audit_id": audit.audit_id,
            "event_id": audit.event_id,
            "record_id": audit.record_id,
            "perspective": audit.perspective,
            "decision": audit.decision,
            "trigger_type": audit.trigger_type,
            "target_golden_id": audit.target_golden_id,
            "absorbed_golden_id": getattr(audit, 'absorbed_golden_id', None),
            "confidence": audit.confidence,
            "dimension_scores": json.dumps(audit.dimension_scores, default=str),
            "reasoning": audit.reasoning,
            "key_factors": json.dumps(audit.key_factors),
            "candidates_evaluated": audit.candidates_evaluated,
            "llm_calls": audit.llm_calls,
            "embedding_calls": audit.embedding_calls,
            "total_duration_ms": audit.total_duration_ms,
            "evaluation_chain": json.dumps(audit.evaluation_chain, default=str),
            "golden_record_before": json.dumps(getattr(audit, 'golden_record_before', None), default=str),
            "golden_record_after": json.dumps(getattr(audit, 'golden_record_after', None), default=str),
            "created_at": now,
        }

    def _deserialize_gr(self, row: dict) -> dict:
        if not row:
            return row
        for col in ["name_variants", "commodity_keywords", "service_categories",
                     "source_records", "bucket_keys"]:
            if row.get(col) and isinstance(row[col], str):
                try:
                    row[col] = json.loads(row[col])
                except json.JSONDecodeError:
                    pass
        if row.get("persona") and isinstance(row["persona"], str):
            try:
                row["persona"] = json.loads(row["persona"])
            except json.JSONDecodeError:
                pass
        # Convert datetime objects to ISO strings for Pydantic compatibility
        for col in ["created_at", "updated_at"]:
            val = row.get(col)
            if val and not isinstance(val, str):
                row[col] = val.isoformat() if hasattr(val, 'isoformat') else str(val)
        return row
