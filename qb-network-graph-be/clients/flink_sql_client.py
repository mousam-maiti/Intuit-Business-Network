"""
Flink SQL Gateway REST client — reads and writes to Paimon tables.

Uses the Flink SQL Gateway REST API (port 8081) to execute SQL statements
against Paimon catalog tables (gold.pending_resolution, gold.resolution_audit, etc.).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Flink SQL Gateway REST API session lifecycle:
# 1. POST /v1/sessions → session_handle
# 2. POST /v1/sessions/{handle}/statements → operation_handle
# 3. GET  /v1/sessions/{handle}/operations/{op}/result/0 → rows


class FlinkSQLClient:
    """Synchronous client for the Flink SQL Gateway REST API."""

    def __init__(self, base_url: str = "http://localhost:8081", timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session_handle: Optional[str] = None
        self._http = httpx.Client(base_url=self._base_url, timeout=timeout)
        self._catalog_configured = False

    def connect(self):
        """Open a session and configure the Paimon catalog."""
        try:
            resp = self._http.post("/v1/sessions", json={})
            resp.raise_for_status()
            self._session_handle = resp.json()["sessionHandle"]
            logger.info(f"Flink SQL session opened: {self._session_handle}")

            # Configure Paimon catalog
            self._execute_statement("USE CATALOG paimon", wait=True)
            self._catalog_configured = True
        except Exception as e:
            logger.warning(f"Flink SQL Gateway unavailable ({e}) — Paimon reads disabled")
            self._session_handle = None

    @property
    def available(self) -> bool:
        return self._session_handle is not None

    def execute_query(self, sql: str, params: list = None) -> list[dict]:
        """Execute a SELECT and return rows as list of dicts."""
        if not self.available:
            return []

        # Substitute params as positional placeholders
        final_sql = self._interpolate(sql, params)
        return self._execute_statement(final_sql, wait=True)

    def execute_update(self, sql: str, params: list = None) -> bool:
        """Execute an INSERT/UPDATE statement. Returns True on success."""
        if not self.available:
            return False

        final_sql = self._interpolate(sql, params)
        try:
            self._execute_statement(final_sql, wait=True)
            return True
        except Exception as e:
            logger.error(f"Flink SQL update failed: {e}")
            return False

    def _execute_statement(self, sql: str, wait: bool = True) -> list[dict]:
        """Submit a SQL statement and optionally wait for results."""
        resp = self._http.post(
            f"/v1/sessions/{self._session_handle}/statements",
            json={"statement": sql},
        )
        resp.raise_for_status()
        op_handle = resp.json()["operationHandle"]

        if not wait:
            return []

        # Poll for completion
        for _ in range(60):
            status_resp = self._http.get(
                f"/v1/sessions/{self._session_handle}/operations/{op_handle}/status"
            )
            status_resp.raise_for_status()
            status = status_resp.json().get("status", "")
            if status == "FINISHED":
                break
            if status in ("ERROR", "CANCELED"):
                error = status_resp.json().get("error", {}).get("message", "Unknown error")
                raise RuntimeError(f"Flink SQL failed: {error}")
            time.sleep(0.5)
        else:
            raise TimeoutError("Flink SQL statement timed out")

        # Fetch results
        result_resp = self._http.get(
            f"/v1/sessions/{self._session_handle}/operations/{op_handle}/result/0"
        )
        result_resp.raise_for_status()
        result = result_resp.json()

        columns = [col["name"] for col in result.get("resultSchema", {}).get("columns", [])]
        rows = []
        for data_row in result.get("data", []):
            fields = data_row.get("fields", [])
            row = {}
            for i, col in enumerate(columns):
                row[col] = fields[i] if i < len(fields) else None
            rows.append(row)
        return rows

    def _interpolate(self, sql: str, params: list = None) -> str:
        """Replace %s placeholders with escaped values for Flink SQL."""
        if not params:
            return sql
        escaped = []
        for p in params:
            if p is None:
                escaped.append("NULL")
            elif isinstance(p, (int, float)):
                escaped.append(str(p))
            elif isinstance(p, bool):
                escaped.append("TRUE" if p else "FALSE")
            elif isinstance(p, (dict, list)):
                escaped.append(f"'{json.dumps(p, default=str).replace(chr(39), chr(39)+chr(39))}'")
            else:
                escaped.append(f"'{str(p).replace(chr(39), chr(39)+chr(39))}'")
        result = sql
        for val in escaped:
            result = result.replace("%s", val, 1)
        return result

    def close(self):
        if self._session_handle:
            try:
                self._http.delete(f"/v1/sessions/{self._session_handle}")
            except Exception:
                pass
        self._http.close()
