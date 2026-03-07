"""Neo4j-backed entity repository — Entity CRUD with vendor/client counts."""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from repositories.base import AbstractEntityRepository

logger = logging.getLogger(__name__)


def _format_ein(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r'\D', '', str(raw))
    if len(digits) == 9:
        return f"{digits[:2]}-{digits[2:]}"
    return raw


def _format_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r'\D', '', str(raw))
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return raw


def _parse_json(val):
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


def _node_to_entity(node: dict, vendor_count: int = 0, client_count: int = 0) -> dict:
    """Transform a Neo4j Entity node dict into the UI Entity shape."""
    persona = _parse_json(node.get("persona")) or {}
    identity = persona.get("identity", {}) if isinstance(persona, dict) else {}
    name_variants = node.get("name_variants") or []
    if isinstance(name_variants, str):
        name_variants = _parse_json(name_variants) or []
    commodities = node.get("commodity_keywords") or []
    if isinstance(commodities, str):
        commodities = _parse_json(commodities) or []

    return {
        "id": node.get("id"),
        "name": node.get("canonical_name"),
        "ein": _format_ein(node.get("ein")),
        "contactName": node.get("contact_name"),
        "email": node.get("email"),
        "phone": _format_phone(node.get("phone_digits")),
        "website": identity.get("website"),
        "industry": node.get("naics_code"),
        "naics": node.get("naics_code"),
        "legalStructure": identity.get("legal_structure"),
        "address": node.get("street_address"),
        "city": node.get("city"),
        "state": node.get("state"),
        "zip": node.get("zip5"),
        "confidence": float(node["confidence"]) if node.get("confidence") is not None else None,
        "vendors": vendor_count,
        "clients": client_count,
        "volume": float(node["total_volume"]) if node.get("total_volume") is not None else 0,
        "variants": name_variants if isinstance(name_variants, list) else [],
        "commodities": commodities if isinstance(commodities, list) else [],
    }


class Neo4jEntityRepository(AbstractEntityRepository):
    """Entity CRUD backed by Neo4j Entity nodes."""

    def __init__(self, driver, database: str):
        self._driver = driver
        self._database = database

    @property
    def available(self) -> bool:
        return self._driver is not None

    def _run(self, cypher: str, params: dict = None) -> list[dict]:
        with self._driver.session(database=self._database) as session:
            result = session.run(cypher, params or {})
            return [dict(record) for record in result]

    def _run_single(self, cypher: str, params: dict = None) -> dict | None:
        records = self._run(cypher, params)
        return records[0] if records else None

    def get_all(self, q: str = None, industry: str = None, company_id: str = None) -> list[dict]:
        if not self.available:
            return []

        if company_id:
            cypher = """
                MATCH (c:Entity {id: $company_id})-[]-(e:Entity)
                WHERE e.status <> 'MERGED'
            """
            params = {"company_id": company_id}
        else:
            cypher = "MATCH (e:Entity) WHERE e.status <> 'MERGED'"
            params = {}

        conditions = []
        if q:
            conditions.append(
                "(e.canonical_name CONTAINS $q OR any(v IN coalesce(e.name_variants, []) WHERE v CONTAINS $q))"
            )
            params["q"] = q
        if industry:
            conditions.append("e.naics_code STARTS WITH $industry")
            params["industry"] = industry

        if conditions:
            cypher += " AND " + " AND ".join(conditions)

        cypher += """
            WITH e
            OPTIONAL MATCH (e)-[bf:BUYS_FROM]->()
            OPTIONAL MATCH (e)-[st:SELLS_TO]->()
            WITH e, count(DISTINCT bf) AS vendor_count, count(DISTINCT st) AS client_count
            RETURN e, vendor_count, client_count
            ORDER BY e.canonical_name
        """
        records = self._run(cypher, params)
        entities = [
            _node_to_entity(dict(r["e"]), r["vendor_count"], r["client_count"])
            for r in records
        ]

        if company_id:
            company_entity = self.get_by_id(company_id)
            if company_entity:
                entities.insert(0, company_entity)

        return entities

    def get_by_id(self, entity_id: str) -> Optional[dict]:
        if not self.available:
            return None
        cypher = """
            MATCH (e:Entity {id: $id})
            OPTIONAL MATCH (e)-[bf:BUYS_FROM]->()
            OPTIONAL MATCH (e)-[st:SELLS_TO]->()
            RETURN e, count(DISTINCT bf) AS vendor_count, count(DISTINCT st) AS client_count
        """
        record = self._run_single(cypher, {"id": entity_id})
        if not record or not record.get("e"):
            return None
        return _node_to_entity(dict(record["e"]), record["vendor_count"], record["client_count"])

    def update(self, entity_id: str, fields: dict) -> Optional[dict]:
        if not self.available:
            return None
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
        params = {"id": entity_id}
        for ui_key, val in fields.items():
            db_prop = field_map.get(ui_key)
            if db_prop:
                param_name = f"p_{db_prop}"
                sets.append(f"e.{db_prop} = ${param_name}")
                if db_prop == "phone_digits":
                    params[param_name] = re.sub(r'\D', '', val) if val else None
                else:
                    params[param_name] = val

        if not sets:
            return self.get_by_id(entity_id)

        cypher = f"MATCH (e:Entity {{id: $id}}) SET {', '.join(sets)}, e.updated_at = datetime()"
        self._run(cypher, params)
        return self.get_by_id(entity_id)

    def batch_fetch(self, node_ids: list[str]) -> list[dict]:
        """Fetch entities with vendor/client counts for a list of IDs."""
        if not node_ids:
            return []
        cypher = """
            UNWIND $ids AS nid
            MATCH (e:Entity {id: nid})
            WHERE e.status <> 'MERGED'
            OPTIONAL MATCH (e)-[bf:BUYS_FROM]->()
            OPTIONAL MATCH (e)-[st:SELLS_TO]->()
            WITH e, count(DISTINCT bf) AS vendor_count, count(DISTINCT st) AS client_count
            RETURN e, vendor_count, client_count
        """
        records = self._run(cypher, {"ids": node_ids})
        return [
            _node_to_entity(dict(r["e"]), r["vendor_count"], r["client_count"])
            for r in records
        ]
