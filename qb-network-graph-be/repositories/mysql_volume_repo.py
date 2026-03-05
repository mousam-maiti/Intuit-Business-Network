"""MySQL-backed volume repository — monthly volume from bills + company source data.

For G- entity IDs, vendor IDs are resolved via Paimon gold.resolution_audit
(queried through Flink SQL) instead of MySQL resolution_audit.
"""
from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from typing import Optional

from repositories.base import AbstractVolumeRepository

logger = logging.getLogger(__name__)


def _format_ein(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 9:
        return f"{digits[:2]}-{digits[2:]}"
    return raw


def _format_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return raw


class MySQLVolumeRepository(AbstractVolumeRepository):
    """Monthly volume and company source data backed by MySQL bills table.

    For G- entity IDs, resolves vendor IDs via Paimon resolution_audit
    (Flink SQL query), then queries MySQL bills for volume.
    """

    def __init__(self, pool, flink_client=None):
        self._pool = pool
        self._flink = flink_client

    @contextmanager
    def _get_conn(self):
        conn = self._pool.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    def _get_vendor_ids_from_paimon(self, entity_id: str) -> list[int]:
        """Resolve vendor IDs for a golden record via Paimon resolution_audit."""
        if not self._flink or not self._flink.available:
            logger.warning("Flink SQL unavailable — cannot resolve vendor IDs for G- entity")
            return []
        try:
            rows = self._flink.execute_query(
                "SELECT DISTINCT record_id FROM gold.resolution_audit "
                "WHERE target_golden_id = %s AND record_id LIKE 'v-%%'",
                [entity_id],
            )
            vendor_ids = []
            for r in rows:
                rid = r.get("record_id", "")
                if rid.startswith("v-"):
                    try:
                        vendor_ids.append(int(rid[2:]))
                    except ValueError:
                        pass
            return vendor_ids
        except Exception as e:
            logger.error(f"Failed to resolve vendor IDs from Paimon: {e}")
            return []

    def get_monthly_volume(self, entity_id: str, company_id: str = None) -> list[dict]:
        months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)

            if entity_id.startswith("G-"):
                # Resolve vendor IDs from Paimon gold.resolution_audit
                vendor_ids = self._get_vendor_ids_from_paimon(entity_id)
                if not vendor_ids:
                    return []

                placeholders = ", ".join(["%s"] * len(vendor_ids))
                sql = f"""
                    SELECT YEAR(b.bill_date) AS yr, MONTH(b.bill_date) AS mo,
                           ROUND(SUM(b.total) / 1000) AS vol
                    FROM bills b
                    WHERE b.vendor_id IN ({placeholders})
                """
                params = list(vendor_ids)
                if company_id:
                    sql += " AND b.company_id = %s"
                    params.append(company_id)
                sql += " GROUP BY YEAR(b.bill_date), MONTH(b.bill_date) ORDER BY yr, mo"
                cursor.execute(sql, params)
            else:
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

    def get_company(self, company_id: str) -> Optional[dict]:
        """Fetch company from source data, return in UI Entity shape."""
        with self._get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM companies WHERE company_id = %s", (company_id,))
            row = cursor.fetchone()
        if not row:
            return None
        cid = str(row["company_id"])
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
            "vendors": 0,
            "clients": 0,
            "volume": total_volume,
            "variants": [row["legal_name"]] if row.get("legal_name") else [],
            "commodities": [row["industry_category"]] if row.get("industry_category") else [],
        }
