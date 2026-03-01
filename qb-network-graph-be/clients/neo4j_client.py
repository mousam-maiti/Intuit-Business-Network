"""
Neo4j client for the REST API backend.

Read-only queries + entity writes against Entity nodes, relationships,
and AuditEntry nodes. Entity shape transformation: Neo4j Entity node → UI Entity dict.
"""
from __future__ import annotations
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from config import Neo4jConfig

logger = logging.getLogger(__name__)

try:
    from neo4j import GraphDatabase
    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False


def _format_ein(raw: str | None) -> str | None:
    """Format EIN as XX-XXXXXXX."""
    if not raw:
        return None
    digits = re.sub(r'\D', '', str(raw))
    if len(digits) == 9:
        return f"{digits[:2]}-{digits[2:]}"
    return raw


def _format_phone(raw: str | None) -> str | None:
    """Format phone as (XXX) XXX-XXXX."""
    if not raw:
        return None
    digits = re.sub(r'\D', '', str(raw))
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


class Neo4jReadClient:
    """Neo4j client for the REST API backend."""

    def __init__(self, cfg: Neo4jConfig):
        self._cfg = cfg
        self._driver = None
        self._available = False

    async def connect(self):
        if not HAS_NEO4J:
            logger.warning("neo4j driver not installed — Neo4j unavailable")
            return
        try:
            self._driver = GraphDatabase.driver(
                self._cfg.uri,
                auth=(self._cfg.user, self._cfg.password),
                max_connection_pool_size=self._cfg.max_pool_size,
            )
            self._driver.verify_connectivity()
            self._available = True
            logger.info(f"Neo4j connected: {self._cfg.uri}")
        except Exception as e:
            logger.warning(f"Neo4j unavailable ({e}) — entity queries disabled")

    async def close(self):
        if self._driver:
            self._driver.close()
            logger.info("Neo4j driver closed")

    @property
    def available(self) -> bool:
        return self._available

    def _run(self, cypher: str, params: dict = None) -> list[dict]:
        """Execute a Cypher query and return list of record dicts."""
        with self._driver.session(database=self._cfg.database) as session:
            result = session.run(cypher, params or {})
            return [dict(record) for record in result]

    def _run_single(self, cypher: str, params: dict = None) -> dict | None:
        """Execute a Cypher query and return first record or None."""
        records = self._run(cypher, params)
        return records[0] if records else None

    # ═══════════════════════════════════════════════════════════
    # ENTITIES
    # ═══════════════════════════════════════════════════════════

    def get_entities(self, q: str = None, industry: str = None, company_id: str = None) -> list[dict]:
        """List entities with vendor/client counts."""
        if not self._available:
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
            OPTIONAL MATCH ()-[vin]->(e)
            OPTIONAL MATCH (e)-[vout]->()
            WITH e, count(DISTINCT vin) AS vendor_count, count(DISTINCT vout) AS client_count
            RETURN e, vendor_count, client_count
            ORDER BY e.canonical_name
        """
        records = self._run(cypher, params)
        entities = [
            _node_to_entity(dict(r["e"]), r["vendor_count"], r["client_count"])
            for r in records
        ]

        # Include the company entity itself when scoping by company_id
        if company_id:
            company_entity = self.get_entity(company_id)
            if company_entity:
                entities.insert(0, company_entity)

        return entities

    def get_entity(self, entity_id: str) -> dict | None:
        """Single entity with vendor/client counts."""
        if not self._available:
            return None
        cypher = """
            MATCH (e:Entity {id: $id})
            OPTIONAL MATCH ()-[vin]->(e)
            OPTIONAL MATCH (e)-[vout]->()
            RETURN e, count(DISTINCT vin) AS vendor_count, count(DISTINCT vout) AS client_count
        """
        record = self._run_single(cypher, {"id": entity_id})
        if not record or not record.get("e"):
            return None
        return _node_to_entity(dict(record["e"]), record["vendor_count"], record["client_count"])

    def patch_entity(self, entity_id: str, fields: dict) -> dict | None:
        """Partial update on Entity node. Maps UI field names to Neo4j properties."""
        if not self._available:
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
            return self.get_entity(entity_id)

        cypher = f"MATCH (e:Entity {{id: $id}}) SET {', '.join(sets)}, e.updated_at = datetime()"
        self._run(cypher, params)
        return self.get_entity(entity_id)

    # ═══════════════════════════════════════════════════════════
    # RELATIONSHIPS
    # ═══════════════════════════════════════════════════════════

    def get_all_relationships(self, company_id: str = None) -> list[dict]:
        if not self._available:
            return []
        if company_id:
            cypher = """
                MATCH (a:Entity)-[r]->(b:Entity)
                WHERE a.id = $cid OR b.id = $cid
                RETURN a.id AS source, b.id AS target,
                       r.volume AS volume, r.count AS count,
                       coalesce(r.status, 'active') AS status
            """
            params = {"cid": company_id}
        else:
            cypher = """
                MATCH (a:Entity)-[r]->(b:Entity)
                RETURN a.id AS source, b.id AS target,
                       r.volume AS volume, r.count AS count,
                       coalesce(r.status, 'active') AS status
            """
            params = {}
        records = self._run(cypher, params)
        return [self._rel_to_dict(r) for r in records]

    def get_entity_relationships(self, entity_id: str) -> list[dict]:
        if not self._available:
            return []
        cypher = """
            MATCH (a:Entity)-[r]->(b:Entity)
            WHERE a.id = $id OR b.id = $id
            RETURN a.id AS source, b.id AS target,
                   r.volume AS volume, r.count AS count,
                   coalesce(r.status, 'active') AS status
        """
        records = self._run(cypher, {"id": entity_id})
        return [self._rel_to_dict(r) for r in records]

    def _rel_to_dict(self, row: dict) -> dict:
        vol = row.get("volume")
        status = row.get("status", "active")
        if not status or status == "ACTIVE":
            status = "active"
        elif status == "DORMANT":
            status = "dormant"
        else:
            status = status.lower()
        return {
            "source": row.get("source"),
            "target": row.get("target"),
            "volume": float(vol) if vol is not None else None,
            "count": row.get("count"),
            "status": status,
        }

    # ═══════════════════════════════════════════════════════════
    # NETWORK (variable-length path)
    # ═══════════════════════════════════════════════════════════

    def get_network(self, entity_id: str, depth: int = 2) -> dict:
        """Ego network: entities + relationships within depth hops."""
        if not self._available:
            return {"entities": [], "relationships": []}

        # Step 1: Collect all node IDs within depth
        cypher = f"""
            MATCH (start:Entity {{id: $id}})
            WITH start, start.id AS sid
            OPTIONAL MATCH (start)-[*1..{depth}]-(n:Entity)
            WHERE n.status <> 'MERGED'
            WITH sid, collect(DISTINCT n.id) AS nids
            RETURN nids + [sid] AS ids
        """
        record = self._run_single(cypher, {"id": entity_id})
        if not record:
            return {"entities": [], "relationships": []}
        node_ids = list(set(record["ids"]))

        # Step 2: Batch-fetch entities with counts
        entities = self._batch_fetch_entities(node_ids)

        # Step 3: Get edges between collected nodes
        relationships = self._get_edges_between(node_ids)

        return {"entities": entities, "relationships": relationships}

    def _batch_fetch_entities(self, node_ids: list[str]) -> list[dict]:
        """Fetch entities with vendor/client counts for a list of IDs."""
        if not node_ids:
            return []
        cypher = """
            UNWIND $ids AS nid
            MATCH (e:Entity {id: nid})
            WHERE e.status <> 'MERGED'
            OPTIONAL MATCH ()-[vin]->(e)
            OPTIONAL MATCH (e)-[vout]->()
            WITH e, count(DISTINCT vin) AS vendor_count, count(DISTINCT vout) AS client_count
            RETURN e, vendor_count, client_count
        """
        records = self._run(cypher, {"ids": node_ids})
        return [
            _node_to_entity(dict(r["e"]), r["vendor_count"], r["client_count"])
            for r in records
        ]

    def _get_edges_between(self, node_ids: list[str]) -> list[dict]:
        """Get all directed edges between a set of node IDs."""
        if not node_ids:
            return []
        cypher = """
            MATCH (a:Entity)-[r]->(b:Entity)
            WHERE a.id IN $ids AND b.id IN $ids
            RETURN DISTINCT a.id AS source, b.id AS target,
                   r.volume AS volume, r.count AS count,
                   coalesce(r.status, 'active') AS status
        """
        records = self._run(cypher, {"ids": node_ids})
        return [self._rel_to_dict(r) for r in records]

    # ═══════════════════════════════════════════════════════════
    # SUPPLY CHAIN (directed traversal)
    # ═══════════════════════════════════════════════════════════

    def get_supply_chain(self, entity_id: str, direction: str = "upstream", max_depth: int = 3) -> dict:
        """Directed traversal: upstream (vendors) or downstream (clients).

        Returns: {"chain": [{"entity": {...}, "depth": N}], "edges": [...]}
        """
        if not self._available:
            return {"chain": [], "edges": []}

        # upstream: entity buys from vendors → follow outgoing edges
        # downstream: clients buy from entity → follow incoming edges
        if direction == "upstream":
            cypher = f"""
                MATCH (start:Entity {{id: $id}})
                OPTIONAL MATCH path = (start)-[*1..{max_depth}]->(n:Entity)
                WHERE n.status <> 'MERGED'
                WITH DISTINCT n, min(length(path)) AS depth
                RETURN n.id AS nid, depth
                ORDER BY depth
            """
        else:
            cypher = f"""
                MATCH (start:Entity {{id: $id}})
                OPTIONAL MATCH path = (start)<-[*1..{max_depth}]-(n:Entity)
                WHERE n.status <> 'MERGED'
                WITH DISTINCT n, min(length(path)) AS depth
                RETURN n.id AS nid, depth
                ORDER BY depth
            """
        records = self._run(cypher, {"id": entity_id})
        depth_map = {entity_id: 0}
        node_ids = [entity_id]
        for r in records:
            if r.get("nid"):
                depth_map[r["nid"]] = r["depth"]
                node_ids.append(r["nid"])

        entities = self._batch_fetch_entities(node_ids)
        entity_map = {e["id"]: e for e in entities}

        chain = []
        for eid, d in sorted(depth_map.items(), key=lambda x: x[1]):
            if eid in entity_map:
                chain.append({"entity": entity_map[eid], "depth": d})

        edges = self._get_edges_between(node_ids)
        return {"chain": chain, "edges": edges}

    # ═══════════════════════════════════════════════════════════
    # SHORTEST PATH
    # ═══════════════════════════════════════════════════════════

    def get_shortest_path(self, id_a: str, id_b: str) -> dict:
        """Shortest path between two entities using Neo4j's built-in shortestPath."""
        if not self._available:
            return {"chain": [], "edges": [], "hops": -1,
                    "message": "Neo4j unavailable"}

        cypher = """
            MATCH (a:Entity {id: $id_a}), (b:Entity {id: $id_b})
            OPTIONAL MATCH path = shortestPath((a)-[*..6]-(b))
            WITH path
            WHERE path IS NOT NULL
            UNWIND nodes(path) AS n
            WITH path, collect({
                id: n.id, name: n.canonical_name,
                state: n.state, naics_code: n.naics_code
            }) AS chain
            UNWIND relationships(path) AS r
            WITH chain, collect({
                source: startNode(r).id, target: endNode(r).id,
                volume: r.volume, count: r.count
            }) AS edges
            RETURN chain, edges
        """
        record = self._run_single(cypher, {"id_a": id_a, "id_b": id_b})
        if not record:
            return {"chain": [], "edges": [], "hops": -1,
                    "message": "No path found between the two entities."}

        chain = record.get("chain", [])
        edges = [self._rel_to_dict(e) for e in (record.get("edges") or [])]
        return {"chain": chain, "edges": edges, "hops": len(edges)}

    # ═══════════════════════════════════════════════════════════
    # COMMON NEIGHBORS
    # ═══════════════════════════════════════════════════════════

    def get_common_neighbors(self, id_a: str, id_b: str, limit: int = 20) -> dict:
        """Find entities connected to both id_a and id_b."""
        if not self._available:
            return {"common_neighbors": [], "count": 0,
                    "entity_a_name": id_a, "entity_b_name": id_b}

        cypher = """
            MATCH (a:Entity {id: $id_a})-[]-(n:Entity)-[]-(b:Entity {id: $id_b})
            WHERE n.id <> $id_a AND n.id <> $id_b AND n.status = 'ACTIVE'
            WITH DISTINCT n
            RETURN n.id AS id, n.canonical_name AS name, n.state AS state,
                   n.naics_code AS naics_code, n.confidence AS confidence
            LIMIT $limit
        """
        records = self._run(cypher, {"id_a": id_a, "id_b": id_b, "limit": limit})
        neighbors = [
            {
                "id": r["id"],
                "name": r.get("name", ""),
                "state": r.get("state", ""),
                "naics_code": r.get("naics_code", ""),
                "confidence": float(r["confidence"]) if r.get("confidence") is not None else None,
            }
            for r in records
        ]

        # Get names for id_a and id_b
        name_cypher = """
            MATCH (e:Entity) WHERE e.id IN [$id_a, $id_b]
            RETURN e.id AS id, e.canonical_name AS name
        """
        name_records = self._run(name_cypher, {"id_a": id_a, "id_b": id_b})
        name_map = {r["id"]: r["name"] for r in name_records}

        return {
            "common_neighbors": neighbors,
            "count": len(neighbors),
            "entity_a_name": name_map.get(id_a, id_a),
            "entity_b_name": name_map.get(id_b, id_b),
        }

    # ═══════════════════════════════════════════════════════════
    # CLUSTER (ego-graph with density)
    # ═══════════════════════════════════════════════════════════

    def get_cluster(self, entity_id: str, max_size: int = 20) -> dict:
        """Ego-graph at depth 3 with density metric."""
        if not self._available:
            return {"entities": [], "relationships": [], "density": 0,
                    "member_count": 0, "top_industries": []}

        # Collect node IDs within 3 hops, limited to max_size
        cypher = f"""
            MATCH (start:Entity {{id: $id}})
            OPTIONAL MATCH (start)-[*1..3]-(n:Entity)
            WHERE n.status <> 'MERGED'
            WITH DISTINCT n
            LIMIT {max_size - 1}
            WITH collect(n.id) AS neighbor_ids
            RETURN [$id] + neighbor_ids AS ids
        """
        record = self._run_single(cypher, {"id": entity_id})
        if not record:
            return {"entities": [], "relationships": [], "density": 0,
                    "member_count": 0, "top_industries": []}

        node_ids = list(set(record["ids"]))
        entities = self._batch_fetch_entities(node_ids)
        relationships = self._get_edges_between(node_ids)

        # Density metric
        n = len(entities)
        max_possible = n * (n - 1) if n > 1 else 1
        density = round(len(relationships) / max_possible, 3)

        # Top industries
        naics_counts = {}
        for e in entities:
            code = e.get("naics") or e.get("industry") or ""
            if code:
                sector = code[:4] if len(code) >= 4 else code
                naics_counts[sector] = naics_counts.get(sector, 0) + 1
        top_industries = sorted(naics_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "entities": entities,
            "relationships": relationships,
            "density": density,
            "member_count": n,
            "top_industries": [{"naics": k, "count": v} for k, v in top_industries],
        }

    # ═══════════════════════════════════════════════════════════
    # IMPACT ANALYSIS (directed traversal)
    # ═══════════════════════════════════════════════════════════

    def get_impact(self, entity_id: str, max_depth: int = 3) -> dict:
        """Find entities that depend on (buy from) this entity."""
        if not self._available:
            return {"affected_entities": [], "affected_count": 0,
                    "total_volume_at_risk": 0, "depth_distribution": {},
                    "concentration_warning": None}

        # Follow incoming edges: (buyer)-[]->(this entity)
        # Multi-hop: (buyer2)-[]->(buyer1)-[]->(entity) — cascading impact
        cypher = f"""
            MATCH (target:Entity {{id: $id}})
            WITH target
            OPTIONAL MATCH path = (affected:Entity)-[*1..{max_depth}]->(target)
            WHERE affected.status = 'ACTIVE' AND affected.id <> target.id
            WITH target, affected, min(length(path)) AS depth
            OPTIONAL MATCH (affected)-[r]->(target)
            RETURN affected.id AS id, affected.canonical_name AS name,
                   affected.state AS state, affected.naics_code AS naics_code,
                   depth, coalesce(r.volume, 0) AS volume_at_risk
            ORDER BY depth
        """
        records = self._run(cypher, {"id": entity_id})

        affected = []
        for r in records:
            affected.append({
                "id": r["id"],
                "name": r.get("name", ""),
                "state": r.get("state", ""),
                "naics_code": r.get("naics_code", ""),
                "depth": r["depth"],
                "volume_at_risk": float(r.get("volume_at_risk") or 0),
            })

        total_vol = sum(a.get("volume_at_risk", 0) for a in affected)
        depth_dist = {}
        for a in affected:
            d = a["depth"]
            depth_dist[d] = depth_dist.get(d, 0) + 1

        # Concentration warning
        concentration = None
        if affected and total_vol > 0:
            depth_1 = [a for a in affected if a["depth"] == 1]
            for a in depth_1:
                vol = a.get("volume_at_risk", 0)
                if vol > total_vol * 0.5:
                    concentration = (f"{a.get('name', a['id'])} accounts for "
                                     f"{vol / total_vol * 100:.0f}% of at-risk volume")
                    break

        return {
            "affected_entities": affected,
            "affected_count": len(affected),
            "total_volume_at_risk": total_vol,
            "depth_distribution": depth_dist,
            "concentration_warning": concentration,
        }

    # ═══════════════════════════════════════════════════════════
    # SEARCH
    # ═══════════════════════════════════════════════════════════

    def search_entities(self, q: str = None, industry: str = None, sort_by: str = None) -> list[dict]:
        if not self._available:
            return []

        if q:
            # Fulltext index search
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
                OPTIONAL MATCH ()-[vin]->(e)
                OPTIONAL MATCH (e)-[vout]->()
                WITH e, score, count(DISTINCT vin) AS vendor_count,
                     count(DISTINCT vout) AS client_count
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
                OPTIONAL MATCH ()-[vin]->(e)
                OPTIONAL MATCH (e)-[vout]->()
                WITH e, count(DISTINCT vin) AS vendor_count,
                     count(DISTINCT vout) AS client_count
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
                        "tier": 1, "match": entity, "confidence": 0.99,
                        "latency": f"{elapsed}ms",
                        "scores": {"name": 1.0, "industry": 1.0, "location": 1.0, "commodity": 1.0},
                    }

        # Tier 2: Fulltext search
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
            OPTIONAL MATCH ()-[vin]->(e)
            OPTIONAL MATCH (e)-[vout]->()
            RETURN e, count(DISTINCT vin) AS vendor_count,
                   count(DISTINCT vout) AS client_count
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
            OPTIONAL MATCH ()-[vin]->(e)
            OPTIONAL MATCH (e)-[vout]->()
            WITH e, score, count(DISTINCT vin) AS vendor_count,
                 count(DISTINCT vout) AS client_count
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

    # ═══════════════════════════════════════════════════════════
    # LINEAGE / AUDIT
    # ═══════════════════════════════════════════════════════════

    def get_lineage_entities(self) -> list[dict]:
        """Distinct golden records that have audit data."""
        if not self._available:
            return []
        cypher = """
            MATCH (a:AuditEntry)
            WITH DISTINCT a.target_golden_id AS gid
            MATCH (e:Entity {id: gid})
            WHERE e.status = 'ACTIVE'
            RETURN e.id AS id, e.canonical_name AS name, e.naics_code AS industry
            ORDER BY e.canonical_name
        """
        return self._run(cypher)

    def get_audit_trail(self, entity_id: str, limit: int = 100) -> list[dict]:
        """Full audit trail for an entity from AuditEntry nodes."""
        if not self._available:
            return []
        cypher = """
            MATCH (a:AuditEntry)
            WHERE a.target_golden_id = $id OR a.absorbed_golden_id = $id
            RETURN a
            ORDER BY a.created_at ASC
            LIMIT $limit
        """
        records = self._run(cypher, {"id": entity_id, "limit": limit})

        json_cols = ("dimension_scores", "key_factors", "evaluation_chain",
                     "golden_record_before", "golden_record_after")
        rows = []
        for r in records:
            entry = dict(r["a"])
            for col in json_cols:
                if col in entry:
                    entry[col] = _parse_json(entry[col])
            entry["entity_id"] = entity_id
            # Serialize Neo4j datetime objects
            for key in ("created_at",):
                val = entry.get(key)
                if val and hasattr(val, "isoformat"):
                    entry[key] = val.isoformat()
                elif val and hasattr(val, "to_native"):
                    entry[key] = val.to_native().isoformat()
            rows.append(entry)
        return rows

    def get_entity_snapshot(self, entity_id: str, date: str) -> dict | None:
        """Last golden_record_after at or before the given date."""
        if not self._available:
            return None
        cypher = """
            MATCH (a:AuditEntry)
            WHERE (a.target_golden_id = $id OR a.absorbed_golden_id = $id)
              AND a.created_at <= datetime($date)
            RETURN a.golden_record_after AS snapshot
            ORDER BY a.created_at DESC
            LIMIT 1
        """
        record = self._run_single(cypher, {"id": entity_id, "date": date})
        if not record:
            return None
        return _parse_json(record.get("snapshot"))

    def restore_entity(self, entity_id: str, snapshot: dict, audit_id: str) -> dict:
        """Restore an entity to a previous snapshot state."""
        if not self._available:
            return {"success": False, "error": "Neo4j unavailable"}

        try:
            # 1. Capture current state as "before"
            current = self._get_entity_raw(entity_id)
            if not current:
                return {"success": False, "error": "Entity not found"}

            # 2. Update Entity node with snapshot values
            set_clauses = []
            params = {"id": entity_id}
            scalar_fields = {
                "canonical_name": "canonical_name", "ein": "ein",
                "phone_digits": "phone_digits", "email": "email",
                "contact_name": "contact_name", "naics_code": "naics_code",
                "naics_sector": "naics_sector", "naics_subsector": "naics_subsector",
                "state": "state", "city": "city", "zip5": "zip5", "zip3": "zip3",
                "street_address": "street_address",
                "total_volume": "total_volume", "avg_transaction": "avg_transaction",
                "transaction_count": "transaction_count", "volume_bracket": "volume_bracket",
                "source_count": "source_count", "confidence": "confidence",
            }
            for snap_key, prop in scalar_fields.items():
                params[f"s_{prop}"] = snapshot.get(snap_key)
                set_clauses.append(f"e.{prop} = $s_{prop}")

            # JSON / list fields
            for field in ("name_variants", "commodity_keywords"):
                val = snapshot.get(field)
                if isinstance(val, str):
                    val = _parse_json(val)
                params[f"s_{field}"] = val if isinstance(val, list) else []
                set_clauses.append(f"e.{field} = $s_{field}")

            persona = snapshot.get("persona")
            if isinstance(persona, dict):
                params["s_persona"] = json.dumps(persona)
            elif isinstance(persona, str):
                params["s_persona"] = persona
            else:
                params["s_persona"] = "{}"
            set_clauses.append("e.persona = $s_persona")
            set_clauses.append("e.updated_at = datetime()")

            cypher = f"MATCH (e:Entity {{id: $id}}) SET {', '.join(set_clauses)}"
            self._run(cypher, params)

            # 3. Get updated state for "after" snapshot
            updated = self._get_entity_raw(entity_id)

            # 4. Write RESTORE audit entry
            new_audit_id = f"A-{uuid.uuid4().hex[:8]}"
            audit_cypher = """
                CREATE (a:AuditEntry {
                    audit_id: $audit_id,
                    event_id: $event_id,
                    record_id: $entity_id,
                    perspective: 'GLOBAL',
                    decision: 'RESTORE',
                    trigger_type: 'USER_ACTION',
                    target_golden_id: $entity_id,
                    confidence: $confidence,
                    reasoning: $reasoning,
                    golden_record_before: $gr_before,
                    golden_record_after: $gr_after,
                    created_at: datetime()
                })
            """
            self._run(audit_cypher, {
                "audit_id": new_audit_id,
                "event_id": f"restore-{audit_id}",
                "entity_id": entity_id,
                "confidence": snapshot.get("confidence", 0),
                "reasoning": f"User restored entity to state from audit {audit_id}",
                "gr_before": json.dumps(current, default=str),
                "gr_after": json.dumps(updated, default=str),
            })

            return {"success": True, "audit_id": new_audit_id}

        except Exception as e:
            logger.error(f"Restore failed for {entity_id}: {e}")
            return {"success": False, "error": str(e)}

    def _get_entity_raw(self, entity_id: str) -> dict | None:
        """Get raw Entity node properties (not transformed to UI shape)."""
        cypher = "MATCH (e:Entity {id: $id}) RETURN e"
        record = self._run_single(cypher, {"id": entity_id})
        if not record or not record.get("e"):
            return None
        node = dict(record["e"])
        # Serialize Neo4j datetime objects for JSON compatibility
        for key in ("created_at", "updated_at"):
            val = node.get(key)
            if val and hasattr(val, "isoformat"):
                node[key] = val.isoformat()
            elif val and hasattr(val, "to_native"):
                node[key] = val.to_native().isoformat()
        return node
