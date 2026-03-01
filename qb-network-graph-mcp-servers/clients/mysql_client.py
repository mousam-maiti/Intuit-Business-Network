"""
MySQL client — source data reads + pending resolution writes.

After the golden record migration to Neo4j (Phase 3), MySQL retains:
  - Source tables: companies, vendors, customers, bills, invoices, payments
  - Pending resolution: OLTP work queue for human review

All golden record CRUD, bucket-key lookups, search, aggregate, audit, and
relationship operations now live in Neo4j (neo4j_client.py).
"""
from __future__ import annotations
import json
import logging
from contextlib import contextmanager
from typing import Optional

from config import MySQLConfig
from models.audit import PendingResolution

logger = logging.getLogger(__name__)

try:
    import mysql.connector
    from mysql.connector import pooling
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False


class MySQLClient:
    """MySQL client for source data reads + pending resolution writes."""

    def __init__(self, cfg: MySQLConfig):
        self._cfg = cfg
        self._pool = None
        self._using_mock = False

        # In-memory fallback for pending resolution
        self._mock_pending: list[dict] = []

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

    async def close(self):
        if self._pool:
            logger.info("MySQL connection pool released")

    @property
    def using_mock(self) -> bool:
        return self._using_mock

    # ═══════════════════════════════════════════════════════════
    # SOURCE DATA READS
    # ═══════════════════════════════════════════════════════════

    def get_company(self, company_id: str) -> Optional[dict]:
        """Read a company row by PK."""
        if self._using_mock:
            return None
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM companies WHERE company_id = %s", (company_id,))
            return cursor.fetchone()

    def get_all_companies(self) -> list[dict]:
        """Read all active company rows."""
        if self._using_mock:
            return []
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM companies WHERE status = 'active'")
            return cursor.fetchall()

    # ═══════════════════════════════════════════════════════════
    # PENDING RESOLUTION (OLTP work queue)
    # ═══════════════════════════════════════════════════════════

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
