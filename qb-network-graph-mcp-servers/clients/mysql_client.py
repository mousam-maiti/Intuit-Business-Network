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

    def get_company(self, company_id: str) -> Optional[dict]:
        """Read a company row by PK."""
        if self._using_mock:
            return None
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM companies WHERE company_id = %s", (company_id,))
            return cursor.fetchone()

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

        # Auto-populate golden_record_after when caller didn't set it
        if audit.golden_record_after is None and audit.target_golden_id:
            gr = self.get_golden_record(audit.target_golden_id)
            if gr:
                audit.golden_record_after = gr

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
                    trigger_type, status, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PENDING', CURRENT_TIMESTAMP(3))
            """, (
                pending.match_id, pending.orphan_golden_id,
                pending.candidate_golden_id, pending.confidence,
                json.dumps(pending.dimension_scores, default=str),
                pending.reasoning, pending.key_uncertainty,
                pending.trigger_type,
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
                cursor.execute("""
                    INSERT INTO pending_resolution (
                        match_id, orphan_golden_id, candidate_golden_id,
                        confidence, dimension_scores, reasoning, key_uncertainty,
                        trigger_type, status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PENDING', CURRENT_TIMESTAMP(3))
                """, (
                    pending.match_id, pending.orphan_golden_id,
                    pending.candidate_golden_id, pending.confidence,
                    json.dumps(pending.dimension_scores, default=str),
                    pending.reasoning, pending.key_uncertainty,
                    pending.trigger_type,
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
    # AGGREGATE / AUDIT QUERIES (new for MCP server)
    # ═══════════════════════════════════════════════════════════

    def aggregate_golden_records(
        self,
        group_by: str,
        state_filter: str = None,
        naics_filter: str = None,
        min_confidence: float = None,
    ) -> list[dict]:
        """GROUP BY query on golden_records for aggregate stats.

        Args:
            group_by: Column to group by (state, naics_sector, naics_subsector, city, volume_bracket)
            state_filter: Optional state filter
            naics_filter: Optional NAICS prefix filter
            min_confidence: Optional minimum confidence threshold

        Returns:
            List of {group_value, count} dicts sorted by count descending.
        """
        allowed_columns = {
            "state": "state",
            "naics_sector": "naics_sector",
            "naics_subsector": "naics_subsector",
            "city": "city",
            "volume_bracket": "volume_bracket",
            "entity_type": "entity_type",
            "industry": "naics_sector",
            "confidence_range": None,  # special handling
        }

        if self._using_mock:
            return self._aggregate_mock(group_by, state_filter, naics_filter, min_confidence)

        col = allowed_columns.get(group_by)
        if group_by == "confidence_range":
            return self._aggregate_confidence_ranges(state_filter, naics_filter, min_confidence)
        if col is None:
            return [{"error": f"Invalid group_by: {group_by}. Allowed: {list(allowed_columns.keys())}"}]

        conditions = ["status != 'MERGED'"]
        params = []
        if state_filter:
            conditions.append("state = %s")
            params.append(state_filter)
        if naics_filter:
            conditions.append("naics_code LIKE %s")
            params.append(f"{naics_filter}%")
        if min_confidence is not None:
            conditions.append("confidence >= %s")
            params.append(min_confidence)

        where = " AND ".join(conditions)
        sql = f"SELECT {col} AS group_value, COUNT(*) AS count FROM golden_records WHERE {where} GROUP BY {col} ORDER BY count DESC"

        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, params)
            return [dict(r) for r in cursor.fetchall()]

    def _aggregate_confidence_ranges(
        self, state_filter: str = None, naics_filter: str = None, min_confidence: float = None,
    ) -> list[dict]:
        """Aggregate by confidence ranges: <0.60, 0.60-0.85, >0.85."""
        conditions = ["status != 'MERGED'"]
        params = []
        if state_filter:
            conditions.append("state = %s")
            params.append(state_filter)
        if naics_filter:
            conditions.append("naics_code LIKE %s")
            params.append(f"{naics_filter}%")
        if min_confidence is not None:
            conditions.append("confidence >= %s")
            params.append(min_confidence)

        where = " AND ".join(conditions)
        sql = f"""
            SELECT
                CASE
                    WHEN confidence >= 0.85 THEN 'high (>=0.85)'
                    WHEN confidence >= 0.60 THEN 'medium (0.60-0.85)'
                    ELSE 'low (<0.60)'
                END AS group_value,
                COUNT(*) AS count
            FROM golden_records
            WHERE {where}
            GROUP BY group_value
            ORDER BY count DESC
        """
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, params)
            return [dict(r) for r in cursor.fetchall()]

    def _aggregate_mock(
        self, group_by: str, state_filter: str = None,
        naics_filter: str = None, min_confidence: float = None,
    ) -> list[dict]:
        """In-memory aggregate for mock mode."""
        from collections import Counter

        field_map = {
            "state": "state", "city": "city", "naics_sector": "naics_sector",
            "naics_subsector": "naics_subsector", "industry": "naics_sector",
            "volume_bracket": "volume_bracket", "entity_type": "entity_type",
        }
        col = field_map.get(group_by, group_by)
        counts: Counter = Counter()

        for gr in self._mock_golden.values():
            if gr.get("status") == "MERGED":
                continue
            if state_filter and gr.get("state") != state_filter:
                continue
            naics = gr.get("naics_code", "") or ""
            if naics_filter and not naics.startswith(naics_filter):
                continue
            conf = float(gr.get("confidence", 0))
            if min_confidence is not None and conf < min_confidence:
                continue

            if group_by == "confidence_range":
                if conf >= 0.85:
                    val = "high (>=0.85)"
                elif conf >= 0.60:
                    val = "medium (0.60-0.85)"
                else:
                    val = "low (<0.60)"
            else:
                # Try flat key first, then nested persona
                val = gr.get(col)
                if val is None:
                    persona = gr.get("persona", {})
                    if isinstance(persona, dict):
                        for dim in persona.values():
                            if isinstance(dim, dict) and col in dim:
                                val = dim[col]
                                break
            if val:
                counts[val] += 1

        return [{"group_value": k, "count": v} for k, v in counts.most_common()]

    def search_by_name(
        self,
        query: str,
        state_filter: str = None,
        city_filter: str = None,
        naics_filter: str = None,
        min_confidence: float = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search golden records by name using MySQL (exact → LIKE → FULLTEXT).

        Three-tier lookup:
          1. Exact match on canonical_name (case-insensitive)
          2. LIKE '%query%' for partial matches
          3. FULLTEXT MATCH AGAINST for word-level search

        Results are deduplicated and exact matches appear first.
        """
        if self._using_mock:
            return []

        conditions_base = ["gr.status != 'MERGED'"]
        params_base = []
        if state_filter:
            conditions_base.append("gr.state = %s")
            params_base.append(state_filter.upper())
        if city_filter:
            conditions_base.append("UPPER(gr.city) = %s")
            params_base.append(city_filter.upper())
        if naics_filter:
            conditions_base.append("gr.naics_code LIKE %s")
            params_base.append(f"{naics_filter}%")
        if min_confidence is not None:
            conditions_base.append("gr.confidence >= %s")
            params_base.append(min_confidence)

        where_base = " AND ".join(conditions_base)
        query_upper = query.strip().upper()

        results = []
        seen_ids = set()

        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)

            # Tier 1: exact match
            sql = f"""
                SELECT gr.golden_record_id, gr.canonical_name, gr.state, gr.city,
                       gr.naics_code, gr.naics_sector, gr.confidence, gr.entity_type,
                       gr.source_count, 1.0 AS match_rank
                FROM golden_records gr
                WHERE UPPER(gr.canonical_name) = %s AND {where_base}
                LIMIT %s
            """
            cursor.execute(sql, (query_upper, *params_base, limit))
            for row in cursor.fetchall():
                rid = row["golden_record_id"]
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    results.append(row)

            # Tier 2: LIKE partial match (any word)
            if len(results) < limit:
                words = [w for w in query_upper.split() if len(w) > 1]
                if words:
                    like_conds = " OR ".join(["UPPER(gr.canonical_name) LIKE %s"] * len(words))
                    like_params = [f"%{w}%" for w in words]
                    sql = f"""
                        SELECT gr.golden_record_id, gr.canonical_name, gr.state, gr.city,
                               gr.naics_code, gr.naics_sector, gr.confidence, gr.entity_type,
                               gr.source_count, 0.8 AS match_rank
                        FROM golden_records gr
                        WHERE ({like_conds}) AND {where_base}
                        ORDER BY gr.confidence DESC
                        LIMIT %s
                    """
                    cursor.execute(sql, (*like_params, *params_base, limit))
                    for row in cursor.fetchall():
                        rid = row["golden_record_id"]
                        if rid not in seen_ids:
                            seen_ids.add(rid)
                            results.append(row)

            # Tier 3: FULLTEXT search (OR logic — any word match)
            if len(results) < limit:
                words = [w for w in query.strip().split() if len(w) > 1]
                ft_query = " ".join(f"{w}*" for w in words)
                if ft_query:
                    sql = f"""
                        SELECT gr.golden_record_id, gr.canonical_name, gr.state, gr.city,
                               gr.naics_code, gr.naics_sector, gr.confidence, gr.entity_type,
                               gr.source_count, 0.6 AS match_rank
                        FROM golden_records gr
                        WHERE MATCH(gr.canonical_name) AGAINST(%s IN BOOLEAN MODE) AND {where_base}
                        ORDER BY gr.confidence DESC
                        LIMIT %s
                    """
                    cursor.execute(sql, (ft_query, *params_base, limit))
                    for row in cursor.fetchall():
                        rid = row["golden_record_id"]
                        if rid not in seen_ids:
                            seen_ids.add(rid)
                            results.append(row)

        return results[:limit]

    def get_relationships(
        self,
        company_id: str,
        connection_type: str = "all",
        sort_by: str = "volume",
        limit: int = 50,
    ) -> list[dict]:
        """Get relationships for a company, filtered by connection type.

        Args:
            company_id: The company's ID.
            connection_type: 'vendor' (company buys from), 'customer' (company sells to), or 'all'.
            sort_by: Sort column: 'volume', 'count', or 'name'.
            limit: Max results.

        Returns:
            List of relationship dicts enriched with golden record fields.
        """
        order_col = {
            "volume": "transaction_volume DESC",
            "count": "transaction_count DESC",
            "name": "canonical_name ASC",
        }.get(sort_by, "transaction_volume DESC")

        if self._using_mock:
            results = []
            for rel in self._mock_relationships.values():
                is_vendor = rel.get("source_entity_id") == company_id
                is_customer = rel.get("target_entity_id") == company_id
                if connection_type == "vendor" and not is_vendor:
                    continue
                if connection_type == "customer" and not is_customer:
                    continue
                if not is_vendor and not is_customer:
                    continue
                other_id = rel.get("target_entity_id") if is_vendor else rel.get("source_entity_id")
                gr = self._mock_golden.get(other_id, {})
                results.append({
                    **rel,
                    "canonical_name": gr.get("canonical_name", ""),
                    "state": gr.get("state", ""),
                    "city": gr.get("city", ""),
                    "naics_code": gr.get("naics_code", ""),
                    "confidence": gr.get("confidence", 0),
                    "entity_type": gr.get("entity_type", ""),
                    "source_count": gr.get("source_count", 1),
                    "connection_type": "vendor" if is_vendor else "customer",
                })
            results.sort(
                key=lambda r: r.get("transaction_volume") or 0, reverse=True)
            return results[:limit]

        # Build query based on connection_type
        if connection_type == "vendor":
            # Company is buyer (source) → vendors are targets
            where = "r.source_entity_id = %s"
            gr_join = "r.target_entity_id"
            conn_label = "'vendor'"
        elif connection_type == "customer":
            # Company is seller (target) → customers are sources
            where = "r.target_entity_id = %s"
            gr_join = "r.source_entity_id"
            conn_label = "'customer'"
        else:
            # Both directions
            where = "(r.source_entity_id = %s OR r.target_entity_id = %s)"
            gr_join = None  # handled below
            conn_label = None

        if connection_type in ("vendor", "customer"):
            sql = f"""
                SELECT r.edge_id, r.source_entity_id, r.target_entity_id,
                       r.transaction_volume, r.transaction_count,
                       r.first_transaction, r.last_transaction,
                       gr.canonical_name, gr.state, gr.city, gr.naics_code,
                       gr.confidence, gr.entity_type, gr.source_count,
                       {conn_label} AS connection_type
                FROM relationships r
                JOIN golden_records gr ON {gr_join} = gr.golden_record_id
                WHERE {where} AND gr.status = 'ACTIVE'
                ORDER BY {order_col}
                LIMIT %s
            """
            params = (company_id, limit)
        else:
            # Union both directions
            sql = f"""
                (SELECT r.edge_id, r.source_entity_id, r.target_entity_id,
                        r.transaction_volume, r.transaction_count,
                        r.first_transaction, r.last_transaction,
                        gr.canonical_name, gr.state, gr.city, gr.naics_code,
                        gr.confidence, gr.entity_type, gr.source_count,
                        'vendor' AS connection_type
                 FROM relationships r
                 JOIN golden_records gr ON r.target_entity_id = gr.golden_record_id
                 WHERE r.source_entity_id = %s AND gr.status = 'ACTIVE')
                UNION ALL
                (SELECT r.edge_id, r.source_entity_id, r.target_entity_id,
                        r.transaction_volume, r.transaction_count,
                        r.first_transaction, r.last_transaction,
                        gr.canonical_name, gr.state, gr.city, gr.naics_code,
                        gr.confidence, gr.entity_type, gr.source_count,
                        'customer' AS connection_type
                 FROM relationships r
                 JOIN golden_records gr ON r.source_entity_id = gr.golden_record_id
                 WHERE r.target_entity_id = %s AND gr.status = 'ACTIVE')
                ORDER BY {order_col}
                LIMIT %s
            """
            params = (company_id, company_id, limit)

        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            for row in rows:
                for col in ["first_transaction", "last_transaction"]:
                    val = row.get(col)
                    if val and not isinstance(val, str):
                        row[col] = val.isoformat() if hasattr(val, 'isoformat') else str(val)
            return rows

    def get_audit_trail(self, entity_id: str, limit: int = 50) -> list[dict]:
        """Retrieve audit trail for a golden record.

        Searches resolution_audit where entity_id appears as target or absorbed.

        Returns:
            List of audit records sorted by created_at descending.
        """
        if self._using_mock:
            results = []
            for a in self._mock_audit:
                if (a.get("target_golden_id") == entity_id or
                        a.get("record_id") == entity_id or
                        a.get("absorbed_golden_id") == entity_id):
                    results.append(a)
            results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return results[:limit]

        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM resolution_audit
                WHERE target_golden_id = %s OR record_id = %s OR absorbed_golden_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (entity_id, entity_id, entity_id, limit))
            rows = cursor.fetchall()
            # Deserialize JSON columns
            for row in rows:
                for col in ["dimension_scores", "key_factors", "evaluation_chain",
                            "golden_record_before", "golden_record_after"]:
                    if row.get(col) and isinstance(row[col], str):
                        try:
                            row[col] = json.loads(row[col])
                        except json.JSONDecodeError:
                            pass
                for col in ["created_at"]:
                    val = row.get(col)
                    if val and not isinstance(val, str):
                        row[col] = val.isoformat() if hasattr(val, 'isoformat') else str(val)
            return rows

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
