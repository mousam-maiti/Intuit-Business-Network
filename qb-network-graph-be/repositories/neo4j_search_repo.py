"""Neo4j-backed search repository — full-text search and ad-hoc resolution."""
from __future__ import annotations

import logging
import re
import time

from repositories.base import AbstractSearchRepository
from repositories.neo4j_entity_repo import _node_to_entity

logger = logging.getLogger(__name__)


class Neo4jSearchRepository(AbstractSearchRepository):
    """Full-text search backed by Neo4j fulltext index."""

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

    def search(self, q: str = None, industry: str = None, sort_by: str = None) -> list[dict]:
        if not self.available:
            return []

        if q:
            cypher = """
                CALL db.index.fulltext.queryNodes('entity_name_ft', $q)
                YIELD node AS e, score
                WHERE e.status <> 'MERGED'
            """
            params = {"q": f"{q}*"}
            if industry:
                cypher += " AND e.naics_code STARTS WITH $industry"
                params["industry"] = industry

            cypher += """
                OPTIONAL MATCH (e)-[bf:BUYS_FROM]->()
                OPTIONAL MATCH (e)-[st:SELLS_TO]->()
                WITH e, score, count(DISTINCT bf) AS vendor_count,
                     count(DISTINCT st) AS client_count
            """
            if sort_by == "volume":
                cypher += " RETURN e, vendor_count, client_count ORDER BY e.total_volume DESC"
            elif sort_by == "confidence":
                cypher += " RETURN e, vendor_count, client_count ORDER BY e.confidence DESC"
            elif sort_by == "connections":
                cypher += " RETURN e, vendor_count, client_count ORDER BY (vendor_count + client_count) DESC"
            else:
                cypher += " RETURN e, vendor_count, client_count ORDER BY score DESC"
        else:
            cypher = "MATCH (e:Entity) WHERE e.status <> 'MERGED'"
            params = {}
            if industry:
                cypher += " AND e.naics_code STARTS WITH $industry"
                params["industry"] = industry

            cypher += """
                OPTIONAL MATCH (e)-[bf:BUYS_FROM]->()
                OPTIONAL MATCH (e)-[st:SELLS_TO]->()
                WITH e, count(DISTINCT bf) AS vendor_count,
                     count(DISTINCT st) AS client_count
            """
            if sort_by == "volume":
                cypher += " RETURN e, vendor_count, client_count ORDER BY e.total_volume DESC"
            elif sort_by == "confidence":
                cypher += " RETURN e, vendor_count, client_count ORDER BY e.confidence DESC"
            elif sort_by == "connections":
                cypher += " RETURN e, vendor_count, client_count ORDER BY (vendor_count + client_count) DESC"
            else:
                cypher += " RETURN e, vendor_count, client_count ORDER BY e.canonical_name"

        records = self._run(cypher, params)
        return [
            _node_to_entity(dict(r["e"]), r["vendor_count"], r["client_count"])
            for r in records
        ]

    def resolve_adhoc(self, name: str = None, ein: str = None,
                      city: str = None, state: str = None,
                      industry: str = None) -> dict:
        start = time.monotonic()

        if ein:
            ein_clean = re.sub(r'\D', '', ein)
            if len(ein_clean) >= 9:
                entity = self._find_by_ein(ein_clean)
                if entity:
                    elapsed = int((time.monotonic() - start) * 1000)
                    return {
                        "tier": 1, "match": entity, "confidence": 0.99,
                        "latency": f"{elapsed}ms",
                        "scores": {"name": 1.0, "industry": 1.0, "location": 1.0, "commodity": 1.0},
                    }

        if name and len(name) > 3:
            candidates = self._fulltext_candidates(name, state, industry)
            if candidates:
                elapsed = int((time.monotonic() - start) * 1000)
                return {"tier": 2, "candidates": candidates, "latency": f"{elapsed}ms"}

        return {"tier": 0, "match": None}

    def _find_by_ein(self, ein_clean: str) -> dict | None:
        cypher = """
            MATCH (e:Entity {ein: $ein})
            WHERE e.status <> 'MERGED'
            OPTIONAL MATCH (e)-[bf:BUYS_FROM]->()
            OPTIONAL MATCH (e)-[st:SELLS_TO]->()
            RETURN e, count(DISTINCT bf) AS vendor_count,
                   count(DISTINCT st) AS client_count
            LIMIT 1
        """
        record = self._run_single(cypher, {"ein": ein_clean})
        if not record or not record.get("e"):
            return None
        return _node_to_entity(dict(record["e"]), record["vendor_count"], record["client_count"])

    def _fulltext_candidates(self, name: str, state: str = None,
                             industry: str = None) -> list[dict]:
        cypher = """
            CALL db.index.fulltext.queryNodes('entity_name_ft', $q)
            YIELD node AS e, score
            WHERE e.status <> 'MERGED'
        """
        params = {"q": f"{name}*"}
        if state:
            cypher += " AND e.state = $state"
            params["state"] = state

        cypher += """
            OPTIONAL MATCH (e)-[bf:BUYS_FROM]->()
            OPTIONAL MATCH (e)-[st:SELLS_TO]->()
            With e, score, count(DISTINCT bf) AS vendor_count,
                 count(DISTINCT st) AS client_count
            RETURN e, score, vendor_count, client_count
            ORDER BY score DESC
            LIMIT 5
        """
        records = self._run(cypher, params)
        candidates = []
        for r in records:
            entity = _node_to_entity(dict(r["e"]), r["vendor_count"], r["client_count"])
            name_score = min(float(r.get("score", 0)) / 10.0, 1.0)
            state_score = 1.0 if state and dict(r["e"]).get("state") == state else 0.5
            naics = dict(r["e"]).get("naics_code") or ""
            industry_score = 1.0 if industry and naics.startswith(industry[:4] if industry else "") else 0.5
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
