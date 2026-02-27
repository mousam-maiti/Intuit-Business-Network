"""
MySQL client for the REST API backend.

Direct queries against golden_records, relationships, and the 4 new tables.
Entity shape transformation: golden_record row -> UI Entity dict.
"""
from __future__ import annotations
import json
import logging
import re
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional

from config import MySQLConfig

logger = logging.getLogger(__name__)

try:
    import mysql.connector
    from mysql.connector import pooling
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False


def _format_ein(raw: str | None) -> str | None:
    """Format EIN as XX-XXXXXXX."""
    if not raw:
        return None
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 9:
        return f"{digits[:2]}-{digits[2:]}"
    return raw


def _format_phone(raw: str | None) -> str | None:
    """Format phone as (XXX) XXX-XXXX."""
    if not raw:
        return None
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return raw


def _parse_json(val):
    """Safely parse a JSON string, returning the parsed value or the original."""
    if val is None:
        return None
    if isinstance(val, (list, dict)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val


def _gr_snapshot(row: dict | None) -> dict | None:
    """Serialize a golden_records row to a JSON-safe dict for audit snapshots."""
    if not row:
        return None
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, (int, float, str, bool, type(None))):
            out[k] = v
        else:
            out[k] = str(v)
    return out


def _to_entity(row: dict, vendor_count: int = 0, client_count: int = 0) -> dict:
    """Transform a golden_records row into the UI Entity shape."""
    persona = _parse_json(row.get("persona")) or {}
    identity = persona.get("identity", {}) if isinstance(persona, dict) else {}
    name_variants = _parse_json(row.get("name_variants")) or []
    commodities = _parse_json(row.get("commodity_keywords")) or []

    return {
        "id": row.get("golden_record_id"),
        "name": row.get("canonical_name"),
        "ein": _format_ein(row.get("ein")),
        "contactName": row.get("contact_name"),
        "email": row.get("email"),
        "phone": _format_phone(row.get("phone_digits")),
        "website": identity.get("website"),
        "industry": row.get("naics_code"),
        "naics": row.get("naics_code"),
        "legalStructure": identity.get("legal_structure"),
        "address": row.get("street_address"),
        "city": row.get("city"),
        "state": row.get("state"),
        "zip": row.get("zip5"),
        "confidence": float(row["confidence"]) if row.get("confidence") is not None else None,
        "vendors": vendor_count,
        "clients": client_count,
        "volume": float(row["total_volume"]) if row.get("total_volume") is not None else 0,
        "variants": name_variants if isinstance(name_variants, list) else [],
        "commodities": commodities if isinstance(commodities, list) else [],
    }


def _time_ago(dt) -> str:
    """Convert a datetime to a human-readable 'X ago' string."""
    if not dt:
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except (ValueError, TypeError):
            return dt
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        m = seconds // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if seconds < 86400:
        h = seconds // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = seconds // 86400
    if d < 7:
        return f"{d} day{'s' if d != 1 else ''} ago"
    w = d // 7
    return f"{w} week{'s' if w != 1 else ''} ago"


class MySQLClient:
    """MySQL client for the REST API backend."""

    def __init__(self, cfg: MySQLConfig):
        self._cfg = cfg
        self._pool = None

    async def connect(self):
        if not HAS_MYSQL:
            raise RuntimeError("mysql-connector-python not installed")
        self._pool = pooling.MySQLConnectionPool(
            pool_name="be_pool",
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

    @contextmanager
    def _get_conn(self):
        conn = self._pool.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    async def close(self):
        logger.info("MySQL connection pool released")

    # ═══════════════════════════════════════════════════════════
    # COMPANY
    # ═══════════════════════════════════════════════════════════

    def get_company(self, company_id: str) -> dict | None:
        """Fetch from companies table, return in UI Entity shape."""
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM companies WHERE company_id = %s", (company_id,))
            row = cursor.fetchone()
        if not row:
            return None
        # Count vendor + client relationships and total bill volume
        cid = str(row["company_id"])
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            # Vendors: company is source (company pays vendor)
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM relationships WHERE source_entity_id = %s",
                (cid,),
            )
            vendor_count = cursor.fetchone()["cnt"]
            # Clients: company is target (client pays company)
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM relationships WHERE target_entity_id = %s",
                (cid,),
            )
            client_count = cursor.fetchone()["cnt"]
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT COALESCE(SUM(total), 0) AS vol FROM bills WHERE company_id = %s",
                (cid,),
            )
            total_volume = float(cursor.fetchone()["vol"])
        return {
            "id": cid,
            "name": row.get("company_name"),
            "ein": _format_ein(row.get("ein")),
            "contactName": row.get("primary_contact"),
            "email": row.get("email"),
            "phone": _format_phone(row.get("phone")),
            "website": row.get("website"),
            "industry": row.get("industry_category"),
            "naics": row.get("industry_category"),
            "legalStructure": row.get("legal_structure"),
            "address": row.get("street_address"),
            "city": row.get("city"),
            "state": row.get("state"),
            "zip": row.get("zip"),
            "confidence": 1.0,
            "vendors": vendor_count,
            "clients": client_count,
            "volume": total_volume,
            "variants": [row["legal_name"]] if row.get("legal_name") else [],
            "commodities": [row["industry_category"]] if row.get("industry_category") else [],
        }

    # ═══════════════════════════════════════════════════════════
    # ENTITIES
    # ═══════════════════════════════════════════════════════════

    def get_entities(self, q: str = None, industry: str = None, company_id: str = None) -> list[dict]:
        """List entities with vendor/client counts. Avoids N+1."""
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)

            conditions = ["gr.status != 'MERGED'"]
            params = []

            # When company_id is provided, scope to entities connected to that company
            # Vendors: company is source → entity is target
            # Customers: entity is source → company is target
            company_join = ""
            if company_id:
                company_join = """
                INNER JOIN (
                    SELECT DISTINCT target_entity_id AS entity_id
                    FROM relationships WHERE source_entity_id = %s
                    UNION
                    SELECT DISTINCT source_entity_id AS entity_id
                    FROM relationships WHERE target_entity_id = %s
                ) company_rels ON gr.golden_record_id = company_rels.entity_id"""
                params.extend([company_id, company_id])

            if q:
                conditions.append(
                    "(gr.canonical_name LIKE %s OR gr.name_variants LIKE %s)"
                )
                like = f"%{q}%"
                params.extend([like, like])
            if industry:
                conditions.append("gr.naics_code LIKE %s")
                params.append(f"{industry}%")

            where = " AND ".join(conditions)
            sql = f"""
                SELECT gr.*,
                       COALESCE(vc.cnt, 0) AS vendor_count,
                       COALESCE(cc.cnt, 0) AS client_count
                FROM golden_records gr
                {company_join}
                LEFT JOIN (
                    SELECT target_entity_id, COUNT(*) cnt
                    FROM relationships GROUP BY target_entity_id
                ) vc ON gr.golden_record_id = vc.target_entity_id
                LEFT JOIN (
                    SELECT source_entity_id, COUNT(*) cnt
                    FROM relationships GROUP BY source_entity_id
                ) cc ON gr.golden_record_id = cc.source_entity_id
                WHERE {where}
                ORDER BY gr.canonical_name
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        entities = [
            _to_entity(r, int(r.get("vendor_count", 0)), int(r.get("client_count", 0)))
            for r in rows
        ]

        # Include the company entity itself when scoping by company_id
        if company_id:
            company = self.get_company(company_id)
            if company:
                entities.insert(0, company)

        return entities

    def get_entity(self, entity_id: str) -> dict | None:
        """Single entity with vendor/client counts."""
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT gr.*,
                       COALESCE(vc.cnt, 0) AS vendor_count,
                       COALESCE(cc.cnt, 0) AS client_count
                FROM golden_records gr
                LEFT JOIN (
                    SELECT target_entity_id, COUNT(*) cnt
                    FROM relationships WHERE target_entity_id = %s
                ) vc ON gr.golden_record_id = vc.target_entity_id
                LEFT JOIN (
                    SELECT source_entity_id, COUNT(*) cnt
                    FROM relationships WHERE source_entity_id = %s
                ) cc ON gr.golden_record_id = cc.source_entity_id
                WHERE gr.golden_record_id = %s
                """,
                (entity_id, entity_id, entity_id),
            )
            row = cursor.fetchone()
        if not row:
            return self.get_company(entity_id)
        return _to_entity(row, int(row.get("vendor_count", 0)), int(row.get("client_count", 0)))

    def patch_entity(self, entity_id: str, fields: dict) -> dict | None:
        """Partial update on golden_records. Maps UI field names to DB columns."""
        field_map = {
            "name": "canonical_name",
            "contactName": "contact_name",
            "email": "email",
            "phone": "phone_digits",
            "address": "street_address",
            "city": "city",
            "state": "state",
            "zip": "zip5",
            "industry": "naics_code",
            "naics": "naics_code",
        }
        sets = []
        params = []
        for ui_key, val in fields.items():
            db_col = field_map.get(ui_key)
            if db_col:
                sets.append(f"{db_col} = %s")
                if db_col == "phone_digits":
                    params.append(re.sub(r'\D', '', val) if val else None)
                else:
                    params.append(val)

        if not sets:
            return self.get_entity(entity_id)

        params.append(entity_id)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE golden_records SET {', '.join(sets)} WHERE golden_record_id = %s",
                params,
            )
            conn.commit()
        return self.get_entity(entity_id)

    # ═══════════════════════════════════════════════════════════
    # RELATIONSHIPS
    # ═══════════════════════════════════════════════════════════

    def get_all_relationships(self, company_id: str = None) -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            if company_id:
                cursor.execute("""
                    SELECT edge_id, source_entity_id, target_entity_id,
                           transaction_volume, transaction_count,
                           first_transaction, last_transaction, status
                    FROM relationships
                    WHERE source_entity_id = %s OR target_entity_id = %s
                """, (company_id, company_id))
            else:
                cursor.execute("""
                    SELECT edge_id, source_entity_id, target_entity_id,
                           transaction_volume, transaction_count,
                           first_transaction, last_transaction, status
                    FROM relationships
                """)
            rows = cursor.fetchall()
        return [self._rel_to_dict(r) for r in rows]

    def get_entity_relationships(self, entity_id: str) -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT edge_id, source_entity_id, target_entity_id,
                       transaction_volume, transaction_count,
                       first_transaction, last_transaction, status
                FROM relationships
                WHERE source_entity_id = %s OR target_entity_id = %s
            """, (entity_id, entity_id))
            rows = cursor.fetchall()
        return [self._rel_to_dict(r) for r in rows]

    def _rel_to_dict(self, row: dict) -> dict:
        vol = row.get("transaction_volume")
        # Use the table's status column if present, else derive from last_transaction
        status = row.get("status", "active")
        if not status or status == "ACTIVE":
            status = "active"
        elif status == "DORMANT":
            status = "dormant"
        else:
            status = status.lower()
        return {
            "source": row.get("source_entity_id"),
            "target": row.get("target_entity_id"),
            "volume": float(vol) if vol is not None else None,
            "count": row.get("transaction_count"),
            "status": status,
        }

    # ═══════════════════════════════════════════════════════════
    # NETWORK (BFS ego graph)
    # ═══════════════════════════════════════════════════════════

    def get_network(self, entity_id: str, depth: int = 2) -> dict:
        """BFS ego network: entities + relationships within depth."""
        visited = {entity_id}
        frontier = {entity_id}
        all_rels = []

        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)

            for _ in range(depth):
                if not frontier:
                    break
                placeholders = ",".join(["%s"] * len(frontier))
                cursor.execute(f"""
                    SELECT edge_id, source_entity_id, target_entity_id,
                           transaction_volume, transaction_count,
                           first_transaction, last_transaction
                    FROM relationships
                    WHERE source_entity_id IN ({placeholders})
                       OR target_entity_id IN ({placeholders})
                """, list(frontier) + list(frontier))
                rows = cursor.fetchall()
                next_frontier = set()
                for r in rows:
                    all_rels.append(r)
                    for eid in [r["source_entity_id"], r["target_entity_id"]]:
                        if eid not in visited:
                            next_frontier.add(eid)
                            visited.add(eid)
                frontier = next_frontier

            # Batch-fetch entities
            if visited:
                placeholders = ",".join(["%s"] * len(visited))
                cursor.execute(f"""
                    SELECT gr.*,
                           COALESCE(vc.cnt, 0) AS vendor_count,
                           COALESCE(cc.cnt, 0) AS client_count
                    FROM golden_records gr
                    LEFT JOIN (
                        SELECT target_entity_id, COUNT(*) cnt
                        FROM relationships GROUP BY target_entity_id
                    ) vc ON gr.golden_record_id = vc.target_entity_id
                    LEFT JOIN (
                        SELECT source_entity_id, COUNT(*) cnt
                        FROM relationships GROUP BY source_entity_id
                    ) cc ON gr.golden_record_id = cc.source_entity_id
                    WHERE gr.golden_record_id IN ({placeholders})
                      AND gr.status != 'MERGED'
                """, list(visited))
                entity_rows = cursor.fetchall()
            else:
                entity_rows = []

        entities = [
            _to_entity(r, int(r.get("vendor_count", 0)), int(r.get("client_count", 0)))
            for r in entity_rows
        ]

        # If seed entity is a company (not in golden_records), include it
        seed_in_results = any(e["id"] == entity_id for e in entities)
        if not seed_in_results:
            company = self.get_company(entity_id)
            if company:
                entities.insert(0, company)

        # Deduplicate rels and keep only those with both endpoints in visited
        seen_edges = set()
        relationships = []
        for r in all_rels:
            eid = r.get("edge_id")
            if eid in seen_edges:
                continue
            seen_edges.add(eid)
            src, tgt = r["source_entity_id"], r["target_entity_id"]
            if src in visited and tgt in visited:
                relationships.append(self._rel_to_dict(r))

        return {"entities": entities, "relationships": relationships}

    # ═══════════════════════════════════════════════════════════
    # MONTHLY VOLUME
    # ═══════════════════════════════════════════════════════════

    def get_monthly_volume(self, entity_id: str, company_id: str = None) -> list[dict]:
        """Monthly volume trend from bills table.
        - Company ID: all bills for that company
        - Golden record ID: bills for vendor IDs resolved to that golden record (scoped to company)
        """
        months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)

            if entity_id.startswith("G-"):
                # Golden record → find vendor IDs via resolution_audit → query bills
                sql = """
                    SELECT YEAR(b.bill_date) AS yr, MONTH(b.bill_date) AS mo,
                           ROUND(SUM(b.total) / 1000) AS vol
                    FROM bills b
                    WHERE b.vendor_id IN (
                        SELECT DISTINCT CAST(SUBSTRING(ra.record_id, 3) AS UNSIGNED)
                        FROM resolution_audit ra
                        WHERE ra.target_golden_id = %s
                          AND ra.record_id LIKE 'v-%%'
                    )
                """
                params = [entity_id]
                if company_id:
                    sql += " AND b.company_id = %s"
                    params.append(company_id)
                sql += " GROUP BY YEAR(b.bill_date), MONTH(b.bill_date) ORDER BY yr, mo"
                cursor.execute(sql, params)
            else:
                # Company ID → all bills for that company
                cursor.execute("""
                    SELECT YEAR(bill_date) AS yr, MONTH(bill_date) AS mo,
                           ROUND(SUM(total) / 1000) AS vol
                    FROM bills
                    WHERE company_id = %s
                    GROUP BY YEAR(bill_date), MONTH(bill_date)
                    ORDER BY yr, mo
                """, (entity_id,))

            rows = cursor.fetchall()
            result = []
            for r in rows:
                mo = int(r["mo"])
                result.append({"month": months[mo], "vol": int(r["vol"] or 0)})
            return result[-12:]

    # ═══════════════════════════════════════════════════════════
    # SEARCH (FULLTEXT)
    # ═══════════════════════════════════════════════════════════

    def search_entities(
        self, q: str = None, industry: str = None, sort_by: str = None,
    ) -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)

            conditions = ["gr.status != 'MERGED'"]
            params = []
            order = "gr.canonical_name ASC"

            if q:
                conditions.append(
                    "MATCH(gr.canonical_name) AGAINST(%s IN BOOLEAN MODE)"
                )
                params.append(f"{q}*")
            if industry:
                conditions.append("gr.naics_code LIKE %s")
                params.append(f"{industry}%")

            if sort_by == "volume":
                order = "gr.total_volume DESC"
            elif sort_by == "confidence":
                order = "gr.confidence DESC"
            elif sort_by == "connections":
                order = "(COALESCE(vc.cnt, 0) + COALESCE(cc.cnt, 0)) DESC"

            where = " AND ".join(conditions)
            sql = f"""
                SELECT gr.*,
                       COALESCE(vc.cnt, 0) AS vendor_count,
                       COALESCE(cc.cnt, 0) AS client_count
                FROM golden_records gr
                LEFT JOIN (
                    SELECT target_entity_id, COUNT(*) cnt
                    FROM relationships GROUP BY target_entity_id
                ) vc ON gr.golden_record_id = vc.target_entity_id
                LEFT JOIN (
                    SELECT source_entity_id, COUNT(*) cnt
                    FROM relationships GROUP BY source_entity_id
                ) cc ON gr.golden_record_id = cc.source_entity_id
                WHERE {where}
                ORDER BY {order}
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        return [
            _to_entity(r, int(r.get("vendor_count", 0)), int(r.get("client_count", 0)))
            for r in rows
        ]

    # ═══════════════════════════════════════════════════════════
    # MATCHING / PENDING RESOLUTION
    # ═══════════════════════════════════════════════════════════

    def get_pending_matches(self) -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT pr.*,
                       og.canonical_name AS orphan_name,
                       og.naics_code AS orphan_naics,
                       og.city AS orphan_city,
                       og.state AS orphan_state
                FROM pending_resolution pr
                LEFT JOIN golden_records og
                    ON pr.orphan_golden_id = og.golden_record_id
                WHERE pr.status = 'PENDING'
                ORDER BY pr.created_at DESC
            """)
            pending_rows = cursor.fetchall()

        results = []
        for pr in pending_rows:
            candidate_entity = None
            cid = pr.get("candidate_golden_id")
            if cid:
                candidate_entity = self.get_entity(cid)

            dim_scores = _parse_json(pr.get("dimension_scores")) or {}
            if "identity" in dim_scores:
                dim_scores["name"] = dim_scores.pop("identity")
            orphan_city = pr.get("orphan_city") or ""
            orphan_state = pr.get("orphan_state") or ""
            location = f"{orphan_city}, {orphan_state}".strip(", ")

            # Shared neighbors: entities connected to both orphan and candidate
            shared = []
            if cid and pr.get("orphan_golden_id"):
                shared = self._get_shared_neighbors(pr["orphan_golden_id"], cid)

            results.append({
                "id": pr.get("match_id"),
                "inputName": pr.get("orphan_name"),
                "inputCategory": pr.get("orphan_naics"),
                "inputLocation": location or None,
                "candidate": candidate_entity,
                "confidence": float(pr["confidence"]) if pr.get("confidence") is not None else None,
                "age": _time_ago(pr.get("created_at")),
                "scores": dim_scores,
                "sharedNeighbors": shared,
                "triggerType": pr.get("trigger_type", "AI_AGENT"),
            })
        return results

    def _get_shared_neighbors(self, id_a: str, id_b: str) -> list[str]:
        """Find entity names connected to both id_a and id_b."""
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT DISTINCT gr.canonical_name
                FROM relationships r1
                JOIN relationships r2 ON (
                    (r1.target_entity_id = r2.target_entity_id AND r1.target_entity_id != %s AND r1.target_entity_id != %s)
                    OR (r1.source_entity_id = r2.source_entity_id AND r1.source_entity_id != %s AND r1.source_entity_id != %s)
                    OR (r1.target_entity_id = r2.source_entity_id AND r1.target_entity_id != %s AND r1.target_entity_id != %s)
                )
                JOIN golden_records gr ON gr.golden_record_id = COALESCE(
                    CASE WHEN r1.target_entity_id NOT IN (%s, %s) THEN r1.target_entity_id END,
                    CASE WHEN r1.source_entity_id NOT IN (%s, %s) THEN r1.source_entity_id END
                )
                WHERE (r1.source_entity_id = %s OR r1.target_entity_id = %s)
                  AND (r2.source_entity_id = %s OR r2.target_entity_id = %s)
                LIMIT 5
            """, (id_a, id_b, id_a, id_b, id_a, id_b,
                  id_a, id_b, id_a, id_b,
                  id_a, id_a, id_b, id_b))
            rows = cursor.fetchall()
        return [r["canonical_name"] for r in rows if r.get("canonical_name")]

    def resolve_match(self, match_id: str, resolution: str) -> dict:
        """Accept or reject a pending match.

        accept → execute full merge (golden records + audit).
        reject → mark pending as REJECTED, mark orphan GR as REJECTED.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        if resolution == "accept":
            self._execute_accepted_merge(match_id, now)
            return {"matchId": match_id, "resolution": resolution, "resolvedAt": now_iso}

        # Reject
        with self._get_conn() as conn:
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    "SELECT orphan_golden_id FROM pending_resolution WHERE match_id = %s",
                    (match_id,),
                )
                pr = cursor.fetchone()
                cursor.execute(
                    "UPDATE pending_resolution SET status = 'REJECTED', reviewer = 'user', reviewed_at = %s WHERE match_id = %s",
                    (now, match_id),
                )
                if pr and pr.get("orphan_golden_id"):
                    cursor.execute(
                        "UPDATE golden_records SET status = 'REJECTED' WHERE golden_record_id = %s",
                        (pr["orphan_golden_id"],),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {"matchId": match_id, "resolution": resolution, "resolvedAt": now_iso}

    def _execute_accepted_merge(self, match_id: str, now: datetime):
        """Single-transaction merge: update survivor GR, mark orphan MERGED, update pending, write audit."""
        with self._get_conn() as conn:
            try:
                cursor = conn.cursor(dictionary=True)

                # 1. Fetch pending_resolution row
                cursor.execute("SELECT * FROM pending_resolution WHERE match_id = %s", (match_id,))
                pr = cursor.fetchone()
                if not pr:
                    raise ValueError(f"Pending resolution {match_id} not found")

                orphan_id = pr["orphan_golden_id"]
                candidate_id = pr["candidate_golden_id"]

                # 2. Fetch both golden records
                cursor.execute("SELECT * FROM golden_records WHERE golden_record_id = %s", (orphan_id,))
                orphan_gr = cursor.fetchone()
                cursor.execute("SELECT * FROM golden_records WHERE golden_record_id = %s", (candidate_id,))
                candidate_gr = cursor.fetchone()
                if not orphan_gr or not candidate_gr:
                    raise ValueError(f"Golden record(s) not found: orphan={orphan_id}, candidate={candidate_id}")

                # 3. Merge into candidate (survivor)
                orphan_variants = _parse_json(orphan_gr.get("name_variants")) or []
                candidate_variants = _parse_json(candidate_gr.get("name_variants")) or []
                merged_variants = list(set(candidate_variants) | set(orphan_variants))

                orphan_sources = _parse_json(orphan_gr.get("source_records")) or []
                candidate_sources = _parse_json(candidate_gr.get("source_records")) or []
                merged_sources = list(set(candidate_sources) | set(orphan_sources))

                new_source_count = len(merged_sources)
                old_confidence = float(candidate_gr["confidence"]) if candidate_gr.get("confidence") is not None else 0.5
                new_confidence = min(0.99, old_confidence + 0.05)

                cursor.execute("""
                    UPDATE golden_records
                    SET name_variants = %s,
                        source_records = %s,
                        source_count = %s,
                        confidence = %s,
                        updated_at = %s
                    WHERE golden_record_id = %s
                """, (
                    json.dumps(merged_variants),
                    json.dumps(merged_sources),
                    new_source_count,
                    new_confidence,
                    now,
                    candidate_id,
                ))

                # 4. Mark orphan as MERGED
                cursor.execute("""
                    UPDATE golden_records
                    SET status = 'MERGED', merged_into = %s, updated_at = %s
                    WHERE golden_record_id = %s
                """, (candidate_id, now, orphan_id))

                # 4b. Migrate orphan's relationships to survivor
                #     First collect existing survivor edges to avoid duplicates
                cursor.execute(
                    "SELECT source_entity_id, target_entity_id FROM relationships WHERE source_entity_id = %s OR target_entity_id = %s",
                    (candidate_id, candidate_id),
                )
                existing = {(r["source_entity_id"], r["target_entity_id"]) for r in cursor.fetchall()}

                cursor.execute(
                    "SELECT edge_id, source_entity_id, target_entity_id FROM relationships WHERE source_entity_id = %s OR target_entity_id = %s",
                    (orphan_id, orphan_id),
                )
                orphan_edges = cursor.fetchall()

                for edge in orphan_edges:
                    new_src = candidate_id if edge["source_entity_id"] == orphan_id else edge["source_entity_id"]
                    new_tgt = candidate_id if edge["target_entity_id"] == orphan_id else edge["target_entity_id"]
                    if new_src == new_tgt:
                        # Self-loop after merge — delete
                        cursor.execute("DELETE FROM relationships WHERE edge_id = %s", (edge["edge_id"],))
                    elif (new_src, new_tgt) in existing:
                        # Duplicate — delete orphan edge
                        cursor.execute("DELETE FROM relationships WHERE edge_id = %s", (edge["edge_id"],))
                    else:
                        cursor.execute(
                            "UPDATE relationships SET source_entity_id = %s, target_entity_id = %s, updated_at = %s WHERE edge_id = %s",
                            (new_src, new_tgt, now, edge["edge_id"]),
                        )
                        existing.add((new_src, new_tgt))

                # 5. Update pending_resolution
                cursor.execute("""
                    UPDATE pending_resolution
                    SET status = 'MERGED', reviewer = 'user', reviewed_at = %s
                    WHERE match_id = %s
                """, (now, match_id))

                # 6. Write resolution_audit with before/after snapshots
                audit_id = f"A-{uuid.uuid4().hex[:8]}"
                trigger_type = pr.get("trigger_type", "AI_AGENT")

                gr_before = _gr_snapshot(candidate_gr)
                # Re-fetch survivor after UPDATE to capture merged state
                cursor.execute("SELECT * FROM golden_records WHERE golden_record_id = %s", (candidate_id,))
                gr_after = _gr_snapshot(cursor.fetchone())

                cursor.execute("""
                    INSERT INTO resolution_audit (
                        audit_id, event_id, record_id, perspective, decision,
                        trigger_type, target_golden_id, absorbed_golden_id,
                        confidence, dimension_scores, reasoning, key_factors,
                        candidates_evaluated, llm_calls, embedding_calls,
                        total_duration_ms, evaluation_chain,
                        golden_record_before, golden_record_after, created_at
                    ) VALUES (
                        %s, %s, %s, 'GLOBAL', 'MERGE',
                        %s, %s, %s,
                        %s, %s, %s, %s,
                        0, 0, 0,
                        0, '[]',
                        %s, %s, %s
                    )
                """, (
                    audit_id,
                    f"user-accept-{match_id}",
                    orphan_id,
                    trigger_type,
                    candidate_id,
                    orphan_id,
                    float(pr["confidence"]) if pr.get("confidence") is not None else 0.0,
                    pr.get("dimension_scores", "{}"),
                    f"User accepted merge of {orphan_id} into {candidate_id}",
                    json.dumps(["user_accepted"]),
                    json.dumps(gr_before),
                    json.dumps(gr_after),
                    now,
                ))

                # 7. Commit
                conn.commit()
                logger.info(f"Accepted merge: {orphan_id} → {candidate_id} (match={match_id})")

            except Exception:
                conn.rollback()
                logger.error(f"Accepted merge ROLLED BACK: match_id={match_id}")
                raise

    def resolve_adhoc(self, name: str = None, ein: str = None,
                      city: str = None, state: str = None,
                      industry: str = None) -> dict:
        """Ad-hoc entity resolution: Tier 0 / 1 / 2."""
        import time
        start = time.monotonic()

        # Tier 1: EIN exact match
        if ein:
            ein_clean = re.sub(r'\D', '', ein)
            if len(ein_clean) >= 9:
                entity = self._find_by_ein(ein_clean)
                if entity:
                    elapsed = int((time.monotonic() - start) * 1000)
                    return {
                        "tier": 1,
                        "match": entity,
                        "confidence": 0.99,
                        "latency": f"{elapsed}ms",
                        "scores": {"name": 1.0, "industry": 1.0, "location": 1.0, "commodity": 1.0},
                    }

        # Tier 2: Name FULLTEXT search
        if name and len(name) > 3:
            candidates = self._fulltext_candidates(name, state, industry)
            if candidates:
                elapsed = int((time.monotonic() - start) * 1000)
                return {
                    "tier": 2,
                    "candidates": candidates,
                    "latency": f"{elapsed}ms",
                }

        # Tier 0: No match
        return {"tier": 0, "match": None}

    def _find_by_ein(self, ein_clean: str) -> dict | None:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT gr.*,
                       COALESCE(vc.cnt, 0) AS vendor_count,
                       COALESCE(cc.cnt, 0) AS client_count
                FROM golden_records gr
                LEFT JOIN (
                    SELECT target_entity_id, COUNT(*) cnt
                    FROM relationships WHERE target_entity_id IN (
                        SELECT golden_record_id FROM golden_records WHERE ein = %s
                    )
                ) vc ON gr.golden_record_id = vc.target_entity_id
                LEFT JOIN (
                    SELECT source_entity_id, COUNT(*) cnt
                    FROM relationships WHERE source_entity_id IN (
                        SELECT golden_record_id FROM golden_records WHERE ein = %s
                    )
                ) cc ON gr.golden_record_id = cc.source_entity_id
                WHERE gr.ein = %s AND gr.status != 'MERGED'
                LIMIT 1
            """, (ein_clean, ein_clean, ein_clean))
            row = cursor.fetchone()
        if not row:
            return None
        return _to_entity(row, int(row.get("vendor_count", 0)), int(row.get("client_count", 0)))

    def _fulltext_candidates(self, name: str, state: str = None,
                             industry: str = None) -> list[dict]:
        """FULLTEXT search returning scored candidates."""
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)

            conditions = [
                "MATCH(gr.canonical_name) AGAINST(%s IN BOOLEAN MODE)",
                "gr.status != 'MERGED'",
            ]
            params = [f"{name}*"]

            if state:
                conditions.append("gr.state = %s")
                params.append(state)

            where = " AND ".join(conditions)
            cursor.execute(f"""
                SELECT gr.*,
                       COALESCE(vc.cnt, 0) AS vendor_count,
                       COALESCE(cc.cnt, 0) AS client_count,
                       MATCH(gr.canonical_name) AGAINST(%s IN BOOLEAN MODE) AS relevance
                FROM golden_records gr
                LEFT JOIN (
                    SELECT target_entity_id, COUNT(*) cnt
                    FROM relationships GROUP BY target_entity_id
                ) vc ON gr.golden_record_id = vc.target_entity_id
                LEFT JOIN (
                    SELECT source_entity_id, COUNT(*) cnt
                    FROM relationships GROUP BY source_entity_id
                ) cc ON gr.golden_record_id = cc.source_entity_id
                WHERE {where}
                ORDER BY relevance DESC
                LIMIT 5
            """, [f"{name}*"] + params)
            rows = cursor.fetchall()

        candidates = []
        for r in rows:
            entity = _to_entity(r, int(r.get("vendor_count", 0)), int(r.get("client_count", 0)))
            # Simple scoring
            name_score = min(float(r.get("relevance", 0)) / 10.0, 1.0)
            state_score = 1.0 if state and r.get("state") == state else 0.5
            industry_score = 1.0 if industry and r.get("naics_code", "").startswith(industry[:4] if industry else "") else 0.5
            confidence = round(name_score * 0.5 + state_score * 0.25 + industry_score * 0.25, 2)
            candidates.append({
                "entity": entity,
                "confidence": confidence,
                "scores": {
                    "name": round(name_score, 2),
                    "industry": round(industry_score, 2),
                    "location": round(state_score, 2),
                    "commodity": 0.5,
                },
            })
        return candidates

    # ═══════════════════════════════════════════════════════════
    # CONNECTIONS
    # ═══════════════════════════════════════════════════════════

    def get_auto_connections(self, user_id: str = "1") -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM auto_connections
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_id,))
            rows = cursor.fetchall()

        results = []
        for r in rows:
            entity = self.get_entity(r["entity_id"])
            results.append({
                "id": r["connection_id"],
                "type": r["conn_type"],
                "source": r.get("source_doc"),
                "sourceDate": r.get("source_date"),
                "entity": entity,
                "resolution": r.get("resolution_type", "auto"),
                "tier": r.get("tier", 1),
                "confidence": float(r["confidence"]) if r.get("confidence") is not None else None,
                "latency": f"{r['latency_ms']}ms" if r.get("latency_ms") else None,
                "time": _time_ago(r.get("created_at")),
            })
        return results

    def get_manual_connections(self, user_id: str = "1") -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM manual_connections
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_id,))
            rows = cursor.fetchall()

        results = []
        for r in rows:
            entity = None
            if r.get("entity_id"):
                entity = self.get_entity(r["entity_id"])
            if not entity:
                entity = _parse_json(r.get("entity_snapshot"))
            results.append({
                "id": r["connection_id"],
                "type": r["conn_type"],
                "entity": entity,
                "addedVia": r.get("added_via"),
                "confidence": float(r["confidence"]) if r.get("confidence") is not None else None,
                "time": _time_ago(r.get("created_at")),
            })
        return results

    def add_connection(self, payload: dict, user_id: str = "1") -> dict:
        conn_id = f"mc-{uuid.uuid4().hex[:8]}"
        conn_type = payload.get("connType", "vendor")
        entity_data = payload.get("entity")
        entity_id = entity_data.get("id") if entity_data else None
        added_via = "Matched to existing entity" if entity_id else "Created as new entity"
        confidence = 0.91 if entity_id else None

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO manual_connections
                    (connection_id, user_id, conn_type, entity_id, entity_snapshot, added_via, confidence)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                conn_id, user_id, conn_type, entity_id,
                json.dumps(entity_data) if entity_data else None,
                added_via, confidence,
            ))
            conn.commit()

        entity = None
        if entity_id:
            entity = self.get_entity(entity_id)
        if not entity:
            entity = entity_data or {
                "id": f"e-{uuid.uuid4().hex[:8]}",
                "name": payload.get("name", "New entity"),
                "industry": "236220",
                "city": payload.get("city", "Unknown"),
                "state": payload.get("state", "TX"),
                "vendors": 0, "clients": 0, "volume": 0, "variants": [],
            }

        return {
            "id": conn_id,
            "type": conn_type,
            "entity": entity,
            "addedVia": added_via,
            "confidence": confidence,
            "time": "Just now",
        }

    # ═══════════════════════════════════════════════════════════
    # ALERTS
    # ═══════════════════════════════════════════════════════════

    def insert_alert(
        self,
        alert_id: str,
        connection_id: str,
        alert_type: str,
        title: str,
        message: str = None,
        entity_name: str = None,
        target_entity_id: str = None,
        confidence: float = None,
        user_id: str = "1",
    ):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO connection_alerts
                    (alert_id, connection_id, user_id, alert_type, title,
                     message, entity_name, target_entity_id, confidence)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                alert_id, connection_id, user_id, alert_type, title,
                message, entity_name, target_entity_id, confidence,
            ))
            conn.commit()

    def get_alerts(self, user_id: str = "1") -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM connection_alerts
                WHERE user_id = %s AND dismissed = FALSE
                ORDER BY created_at DESC
                LIMIT 20
            """, (user_id,))
            rows = cursor.fetchall()
        return [
            {
                "id": r["alert_id"],
                "connectionId": r["connection_id"],
                "type": r["alert_type"],
                "title": r["title"],
                "message": r.get("message"),
                "entityName": r.get("entity_name"),
                "targetEntityId": r.get("target_entity_id"),
                "confidence": float(r["confidence"]) if r.get("confidence") is not None else None,
                "time": _time_ago(r.get("created_at")),
            }
            for r in rows
        ]

    def dismiss_alert(self, alert_id: str):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE connection_alerts SET dismissed = TRUE WHERE alert_id = %s",
                (alert_id,),
            )
            conn.commit()

    def update_connection_agent_status(
        self,
        connection_id: str,
        status: str,
        decision: str = None,
        golden_record_id: str = None,
    ):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE manual_connections
                SET agent_status = %s,
                    agent_decision = %s,
                    agent_golden_record_id = %s,
                    agent_resolved_at = CURRENT_TIMESTAMP(3)
                WHERE connection_id = %s
            """, (status, decision, golden_record_id, connection_id))
            conn.commit()

    # ═══════════════════════════════════════════════════════════
    # NATIVE OVERRIDES
    # ═══════════════════════════════════════════════════════════

    def get_all_overrides(self, user_id: str = "1") -> dict:
        """Returns {entityId: {field: value, ...}, ...}."""
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT entity_id, overrides FROM native_overrides WHERE user_id = %s",
                (user_id,),
            )
            rows = cursor.fetchall()
        result = {}
        for r in rows:
            result[r["entity_id"]] = _parse_json(r["overrides"]) or {}
        return result

    def get_override(self, entity_id: str, user_id: str = "1") -> dict | None:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT overrides FROM native_overrides WHERE user_id = %s AND entity_id = %s",
                (user_id, entity_id),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return _parse_json(row["overrides"])

    def save_override(self, entity_id: str, fields: dict, user_id: str = "1") -> dict:
        """JSON_MERGE_PATCH upsert."""
        fields_json = json.dumps(fields)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO native_overrides (user_id, entity_id, overrides)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE overrides = JSON_MERGE_PATCH(overrides, VALUES(overrides))
            """, (user_id, entity_id, fields_json))
            conn.commit()
        return self.get_override(entity_id, user_id)

    def delete_override_field(self, entity_id: str, field: str, user_id: str = "1") -> dict | None:
        """Remove a single field from the overrides JSON."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE native_overrides
                SET overrides = JSON_REMOVE(overrides, %s)
                WHERE user_id = %s AND entity_id = %s
            """, (f"$.{field}", user_id, entity_id))
            conn.commit()

            # Clean up if empty
            cursor2 = conn.cursor(dictionary=True)
            cursor2.execute(
                "SELECT overrides FROM native_overrides WHERE user_id = %s AND entity_id = %s",
                (user_id, entity_id),
            )
            row = cursor2.fetchone()
            if row:
                overrides = _parse_json(row["overrides"])
                if not overrides or overrides == {}:
                    cursor.execute(
                        "DELETE FROM native_overrides WHERE user_id = %s AND entity_id = %s",
                        (user_id, entity_id),
                    )
                    conn.commit()
                    return None
                return overrides
        return None

    # ═══════════════════════════════════════════════════════════
    # NATIVE MERGES
    # ═══════════════════════════════════════════════════════════

    def get_merges(self, user_id: str = "1") -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM native_merges
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_id,))
            rows = cursor.fetchall()
        return [self._merge_to_dict(r) for r in rows]

    def create_merge(self, payload: dict, user_id: str = "1") -> dict:
        merge_id = f"nm-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        migrated = json.dumps(payload.get("migratedRelationships", []))

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO native_merges
                    (merge_id, user_id, source_entity_id, target_entity_id,
                     origin, reason, migrated_relationships)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                merge_id, user_id,
                payload["sourceEntityId"], payload["targetEntityId"],
                "user", payload.get("reason", ""),
                migrated,
            ))
            conn.commit()

        return {
            "id": merge_id,
            "sourceEntityId": payload["sourceEntityId"],
            "targetEntityId": payload["targetEntityId"],
            "origin": "user",
            "reason": payload.get("reason", ""),
            "migratedRelationships": payload.get("migratedRelationships", []),
            "timestamp": now,
        }

    def delete_merge(self, merge_id: str, user_id: str = "1") -> dict | None:
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM native_merges WHERE merge_id = %s AND user_id = %s",
                (merge_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            result = self._merge_to_dict(row)
            cursor.execute(
                "DELETE FROM native_merges WHERE merge_id = %s AND user_id = %s",
                (merge_id, user_id),
            )
            conn.commit()
        return result

    # ═══════════════════════════════════════════════════════════
    # LINEAGE / AUDIT
    # ═══════════════════════════════════════════════════════════

    def get_lineage_entities(self) -> list[dict]:
        """Distinct golden records that have audit data."""
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT DISTINCT ra.target_golden_id AS id,
                       gr.canonical_name AS name, gr.naics_code AS industry
                FROM resolution_audit ra
                JOIN golden_records gr ON gr.golden_record_id = ra.target_golden_id
                WHERE gr.status = 'ACTIVE'
                ORDER BY gr.canonical_name
            """)
            return cursor.fetchall()

    def get_audit_trail(self, entity_id: str, limit: int = 100) -> list[dict]:
        """Full audit trail for an entity, ascending by date."""
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM resolution_audit
                WHERE target_golden_id = %s OR absorbed_golden_id = %s
                ORDER BY created_at ASC
                LIMIT %s
            """, (entity_id, entity_id, limit))
            rows = cursor.fetchall()

        json_cols = ("dimension_scores", "key_factors", "evaluation_chain",
                     "golden_record_before", "golden_record_after")
        for row in rows:
            for col in json_cols:
                if col in row:
                    row[col] = _parse_json(row[col])
            row["entity_id"] = entity_id
            # Serialize datetimes for JSON response
            for key in ("created_at",):
                val = row.get(key)
                if val and hasattr(val, "isoformat"):
                    row[key] = val.isoformat()
        return rows

    def get_entity_snapshot(self, entity_id: str, date: str) -> dict | None:
        """Last golden_record_after at or before the given date."""
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT golden_record_after FROM resolution_audit
                WHERE (target_golden_id = %s OR absorbed_golden_id = %s)
                  AND created_at <= %s
                ORDER BY created_at DESC LIMIT 1
            """, (entity_id, entity_id, date))
            row = cursor.fetchone()
        if not row:
            return None
        return _parse_json(row["golden_record_after"])

    def restore_entity(self, entity_id: str, snapshot: dict, audit_id: str) -> dict:
        """Restore a golden record to a previous snapshot state.

        Writes the snapshot fields back to golden_records and creates
        a RESTORE audit entry referencing the source audit_id.
        """
        now = datetime.now(timezone.utc)

        with self._get_conn() as conn:
            try:
                cursor = conn.cursor(dictionary=True)

                # 1. Capture current state as "before"
                cursor.execute("SELECT * FROM golden_records WHERE golden_record_id = %s",
                               (entity_id,))
                current = cursor.fetchone()
                if not current:
                    return {"success": False, "error": "Entity not found"}
                gr_before = _gr_snapshot(current)

                # 2. Update golden_records with snapshot values
                cursor.execute("""
                    UPDATE golden_records SET
                        canonical_name = %s, ein = %s, phone_digits = %s,
                        email = %s, contact_name = %s,
                        naics_code = %s, naics_sector = %s, naics_subsector = %s,
                        state = %s, city = %s, zip5 = %s, zip3 = %s,
                        street_address = %s, commodity_keywords = %s,
                        total_volume = %s, avg_transaction = %s,
                        transaction_count = %s, volume_bracket = %s,
                        source_count = %s, confidence = %s,
                        name_variants = %s, persona = %s,
                        updated_at = %s
                    WHERE golden_record_id = %s
                """, (
                    snapshot.get("canonical_name"),
                    snapshot.get("ein"),
                    snapshot.get("phone_digits"),
                    snapshot.get("email"),
                    snapshot.get("contact_name"),
                    snapshot.get("naics_code"),
                    snapshot.get("naics_sector"),
                    snapshot.get("naics_subsector"),
                    snapshot.get("state"),
                    snapshot.get("city"),
                    snapshot.get("zip5"),
                    snapshot.get("zip3"),
                    snapshot.get("street_address"),
                    json.dumps(snapshot.get("commodity_keywords")) if isinstance(snapshot.get("commodity_keywords"), (list, dict)) else snapshot.get("commodity_keywords"),
                    snapshot.get("total_volume"),
                    snapshot.get("avg_transaction"),
                    snapshot.get("transaction_count"),
                    snapshot.get("volume_bracket"),
                    snapshot.get("source_count"),
                    snapshot.get("confidence"),
                    json.dumps(snapshot.get("name_variants")) if isinstance(snapshot.get("name_variants"), (list, dict)) else snapshot.get("name_variants"),
                    json.dumps(snapshot.get("persona")) if isinstance(snapshot.get("persona"), (dict,)) else snapshot.get("persona"),
                    now,
                    entity_id,
                ))

                # 3. Re-read the updated row for "after"
                cursor.execute("SELECT * FROM golden_records WHERE golden_record_id = %s",
                               (entity_id,))
                gr_after = _gr_snapshot(cursor.fetchone())

                # 4. Insert RESTORE audit entry
                new_audit_id = f"A-{uuid.uuid4().hex[:8]}"
                cursor.execute("""
                    INSERT INTO resolution_audit (
                        audit_id, event_id, record_id, perspective, decision,
                        trigger_type, target_golden_id,
                        confidence, reasoning,
                        golden_record_before, golden_record_after, created_at
                    ) VALUES (%s, %s, %s, 'GLOBAL', 'RESTORE',
                              'USER_ACTION', %s,
                              %s, %s,
                              %s, %s, %s)
                """, (
                    new_audit_id,
                    f"restore-{audit_id}",
                    entity_id,
                    entity_id,
                    snapshot.get("confidence", 0),
                    f"User restored entity to state from audit {audit_id}",
                    json.dumps(gr_before, default=str),
                    json.dumps(gr_after, default=str),
                    now,
                ))

                conn.commit()
                return {"success": True, "audit_id": new_audit_id}

            except Exception as e:
                conn.rollback()
                logger.error(f"Restore ROLLED BACK for {entity_id}: {e}")
                return {"success": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════
    # NATIVE MERGES
    # ═══════════════════════════════════════════════════════════

    def _merge_to_dict(self, row: dict) -> dict:
        created = row.get("created_at")
        if created and not isinstance(created, str):
            created = created.isoformat() if hasattr(created, 'isoformat') else str(created)
        return {
            "id": row["merge_id"],
            "sourceEntityId": row["source_entity_id"],
            "targetEntityId": row["target_entity_id"],
            "origin": row.get("origin", "user"),
            "reason": row.get("reason"),
            "migratedRelationships": _parse_json(row.get("migrated_relationships")) or [],
            "timestamp": created,
        }
