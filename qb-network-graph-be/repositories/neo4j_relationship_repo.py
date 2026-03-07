"""Neo4j-backed relationship repository — graph traversal, network, supply chain."""
from __future__ import annotations

import logging

from repositories.base import AbstractRelationshipRepository

logger = logging.getLogger(__name__)


class Neo4jRelationshipRepository(AbstractRelationshipRepository):
    """Graph traversal backed by Neo4j Entity/relationship nodes."""

    def __init__(self, driver, database: str, entity_repo):
        self._driver = driver
        self._database = database
        self._entity_repo = entity_repo

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

    @staticmethod
    def _rel_to_dict(row: dict) -> dict:
        vol = row.get("volume")
        status = row.get("status", "active")
        if not status or status == "ACTIVE":
            status = "active"
        elif status == "DORMANT":
            status = "dormant"
        else:
            status = status.lower()
        rel_type = row.get("rel_type", "")
        return {
            "source": row.get("source"),
            "target": row.get("target"),
            "relType": "vendor" if rel_type == "BUYS_FROM" else "client",
            "volume": float(vol) if vol is not None else None,
            "count": row.get("count"),
            "status": status,
        }

    def get_all(self, company_id: str = None) -> list[dict]:
        if not self.available:
            return []
        if company_id:
            cypher = """
                MATCH (a:Entity)-[r]->(b:Entity)
                WHERE a.id = $cid OR b.id = $cid
                RETURN a.id AS source, b.id AS target, type(r) AS rel_type,
                       r.volume AS volume, r.count AS count,
                       coalesce(r.status, 'active') AS status
            """
            params = {"cid": company_id}
        else:
            cypher = """
                MATCH (a:Entity)-[r]->(b:Entity)
                RETURN a.id AS source, b.id AS target, type(r) AS rel_type,
                       r.volume AS volume, r.count AS count,
                       coalesce(r.status, 'active') AS status
            """
            params = {}
        records = self._run(cypher, params)
        return [self._rel_to_dict(r) for r in records]

    def get_for_entity(self, entity_id: str) -> list[dict]:
        if not self.available:
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

    def _get_edges_between(self, node_ids: list[str]) -> list[dict]:
        if not node_ids:
            return []
        cypher = """
            MATCH (a:Entity)-[r]->(b:Entity)
            WHERE a.id IN $ids AND b.id IN $ids
            RETURN DISTINCT a.id AS source, b.id AS target, type(r) AS rel_type,
                   r.volume AS volume, r.count AS count,
                   coalesce(r.status, 'active') AS status
        """
        records = self._run(cypher, {"ids": node_ids})
        return [self._rel_to_dict(r) for r in records]

    def get_network(self, entity_id: str, depth: int = 2) -> dict:
        if not self.available:
            return {"entities": [], "relationships": []}

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

        entities = self._entity_repo.batch_fetch(node_ids)
        relationships = self._get_edges_between(node_ids)
        return {"entities": entities, "relationships": relationships}

    def get_supply_chain(self, entity_id: str, direction: str = "upstream", max_depth: int = 3) -> dict:
        if not self.available:
            return {"chain": [], "edges": []}

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

        entities = self._entity_repo.batch_fetch(node_ids)
        entity_map = {e["id"]: e for e in entities}

        chain = []
        for eid, d in sorted(depth_map.items(), key=lambda x: x[1]):
            if eid in entity_map:
                chain.append({"entity": entity_map[eid], "depth": d})

        edges = self._get_edges_between(node_ids)
        return {"chain": chain, "edges": edges}

    def get_shortest_path(self, id_a: str, id_b: str) -> dict:
        if not self.available:
            return {"chain": [], "edges": [], "hops": -1, "message": "Neo4j unavailable"}

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

    def get_common_neighbors(self, id_a: str, id_b: str, limit: int = 20) -> dict:
        if not self.available:
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

    def get_cluster(self, entity_id: str, max_size: int = 20) -> dict:
        if not self.available:
            return {"entities": [], "relationships": [], "density": 0,
                    "member_count": 0, "top_industries": []}

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
        entities = self._entity_repo.batch_fetch(node_ids)
        relationships = self._get_edges_between(node_ids)

        n = len(entities)
        max_possible = n * (n - 1) if n > 1 else 1
        density = round(len(relationships) / max_possible, 3)

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

    def get_impact(self, entity_id: str, max_depth: int = 3) -> dict:
        if not self.available:
            return {"affected_entities": [], "affected_count": 0,
                    "total_volume_at_risk": 0, "depth_distribution": {},
                    "concentration_warning": None}

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
