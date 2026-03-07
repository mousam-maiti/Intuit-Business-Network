"""
Direct Paimon table client via pypaimon — reads and writes warehouse files without Flink SQL Gateway.

Uses pypaimon to scan and write Paimon tables directly from the filesystem warehouse.
Write path mirrors the Java PaimonGoldWriter: batch write → prepare commit → commit.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal
from datetime import datetime
from typing import Optional

import pandas as pd
import pyarrow as pa
from pypaimon import CatalogFactory
from pypaimon.manifest.manifest_file_manager import ManifestFileManager

logger = logging.getLogger(__name__)


def _patch_paimon_compat():
    """Patch pypaimon 1.3 to handle Paimon 0.8 manifest format."""
    _orig = ManifestFileManager._get_value_stats_fields

    def _patched(self, file_dict, schema_fields):
        if '_VALUE_STATS_COLS' not in file_dict:
            file_dict['_VALUE_STATS_COLS'] = None
        return _orig(self, file_dict, schema_fields)

    ManifestFileManager._get_value_stats_fields = _patched


_patch_paimon_compat()


class PaimonClient:
    """Read/write client for Paimon tables via pypaimon filesystem catalog."""

    def __init__(self, warehouse_path: str):
        self._warehouse = warehouse_path
        self._catalog = None
        self._available = False

    def connect(self):
        try:
            self._catalog = CatalogFactory.create({'warehouse': self._warehouse})
            self._available = True
            logger.info(f"Paimon catalog connected: {self._warehouse}")
        except Exception as e:
            logger.warning(f"Paimon catalog unavailable ({e})")
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def read_table(self, table_name: str, columns: list[str] = None) -> list[dict]:
        """Read all rows from a Paimon table. Returns list of dicts."""
        if not self._available:
            return []
        try:
            table = self._catalog.get_table(table_name)
            rb = table.new_read_builder()
            if columns:
                rb = rb.with_projection(columns)
            splits = rb.new_scan().plan().splits()
            if not splits:
                return []

            reader = rb.new_read()
            dfs = []
            for s in splits:
                arrow_tbl = reader.to_arrow([s])
                dfs.append(arrow_tbl.to_pandas())
            df = pd.concat(dfs, ignore_index=True)
            return df.to_dict('records')
        except Exception as e:
            logger.error(f"Failed to read Paimon table {table_name}: {e}")
            return []

    def query(self, table_name: str, columns: list[str] = None,
              filters: dict = None) -> list[dict]:
        """Read from a Paimon table with simple equality filters.

        Args:
            table_name: Fully qualified table name (e.g. 'gold.resolution_audit').
            columns: Optional list of columns to project.
            filters: Optional dict of {column: value} equality filters (applied post-read).
        """
        rows = self.read_table(table_name, columns)
        if not filters:
            return rows
        result = []
        for row in rows:
            match = True
            for col, val in filters.items():
                row_val = row.get(col)
                if row_val != val:
                    match = False
                    break
            if match:
                result.append(row)
        return result

    @staticmethod
    def _paimon_to_arrow_type(paimon_type: str):
        """Convert a Paimon type string to a PyArrow type."""
        t = paimon_type.strip().replace(" NOT NULL", "")
        m = re.match(r"DECIMAL\((\d+),\s*(\d+)\)", t)
        if m:
            return pa.decimal128(int(m.group(1)), int(m.group(2)))
        m = re.match(r"TIMESTAMP\((\d+)\)", t)
        if m:
            unit = "ms" if int(m.group(1)) == 3 else "us"
            return pa.timestamp(unit)
        return {"STRING": pa.string(), "INT": pa.int32(), "BIGINT": pa.int64(), "DATE": pa.date32()}.get(t, pa.string())

    @staticmethod
    def _coerce_value(val, paimon_type: str):
        """Coerce a Python value to match the Paimon type."""
        if val is None:
            return None
        # Handle pandas NaN/NaT and float nan
        if isinstance(val, float) and (val != val):  # NaN check
            return None
        if str(val) == "NaT":
            return None
        t = paimon_type.strip().replace(" NOT NULL", "")
        if "DECIMAL" in t:
            m = re.match(r"DECIMAL\((\d+),\s*(\d+)\)", t)
            scale = int(m.group(2)) if m else 3
            return Decimal(str(round(float(val), scale)))
        if "TIMESTAMP" in t:
            if isinstance(val, str):
                return pd.Timestamp(val)
            if isinstance(val, datetime):
                return pd.Timestamp(val)
            return val
        if t in ("INT", "BIGINT"):
            return int(val)
        if t == "DATE":
            if isinstance(val, str):
                return datetime.strptime(val, "%Y-%m-%d").date()
            return val
        return str(val) if not isinstance(val, str) else val

    def write_row(self, table_name: str, row: dict):
        """Write (upsert) a single row to a Paimon table via batch write API.

        Paimon's deduplicate merge engine merges on primary key, so partial
        rows with just the PK + changed fields work as upserts.
        Uses PyArrow table with explicit schema to handle DECIMAL/TIMESTAMP types.
        """
        if not self._available:
            raise RuntimeError("Paimon catalog not connected")
        table = self._catalog.get_table(table_name)
        field_types = {f.name: str(f.type) for f in table.fields}

        pk_set = set(table.primary_keys)

        # Build Arrow arrays with correct types
        arrow_fields = []
        arrow_arrays = []
        for col in table.field_names:
            ptype = field_types[col]
            val = row.get(col)
            atype = self._paimon_to_arrow_type(ptype)
            nullable = col not in pk_set
            coerced = self._coerce_value(val, ptype)
            arrow_fields.append(pa.field(col, atype, nullable=nullable))
            arrow_arrays.append(pa.array([coerced], type=atype))

        arrow_schema = pa.schema(arrow_fields)
        arrow_table = pa.table({f.name: a for f, a in zip(arrow_fields, arrow_arrays)}, schema=arrow_schema)

        wb = table.new_batch_write_builder()
        write = wb.new_write()
        commit = wb.new_commit()
        try:
            write.write_arrow(arrow_table)
            messages = write.prepare_commit()
            commit.commit(messages)
            logger.debug(f"Wrote row to {table_name}: PK={row.get(table.field_names[0])}")
        finally:
            write.close()
            commit.close()

    def close(self):
        self._catalog = None
        self._available = False
