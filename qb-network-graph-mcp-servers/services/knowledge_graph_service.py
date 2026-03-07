"""
Knowledge graph service — ontology queries, graph analytics.

Business logic extracted from knowledge_graph_tools.py.
"""
from __future__ import annotations

import logging
import time

from interfaces.entity_repository import AbstractEntityRepository
from interfaces.relationship_repository import AbstractRelationshipRepository
from interfaces.cache_provider import AbstractCacheProvider

logger = logging.getLogger(__name__)


class KnowledgeGraphService:
    """Ontology queries, shared context, graph analytics."""

    def __init__(
        self,
        entity_repo: AbstractEntityRepository,
        relationship_repo: AbstractRelationshipRepository,
        cache: AbstractCacheProvider,
    ):
        self._entity_repo = entity_repo
        self._rel_repo = relationship_repo
        self._cache = cache

    def query_ontology(self, query_type: str, code_a: str, code_b: str) -> dict:
        """Query T-Box ontology for semantic relationships."""
        if query_type == "INDUSTRY_RELATION":
            return self._query_industry_relation(code_a, code_b)
        elif query_type == "COMMODITY_RELATION":
            return self._query_commodity_relation(code_a, code_b)
        elif query_type == "GEO_CONTAINMENT":
            return self._query_geo_containment(code_a, code_b)
        return {"error": f"Unknown query_type: {query_type}"}

    def _query_industry_relation(self, code_a: str, code_b: str) -> dict:
        start = time.time()
        from clients.neo4j_client import Neo4jClient
        path_a = Neo4jClient.query_naics_hierarchy(code_a)
        path_b = Neo4jClient.query_naics_hierarchy(code_b)
        lca = Neo4jClient.query_lowest_common_ancestor(code_a, code_b)

        # Cross-taxonomy links via Neo4j if entity_repo is Neo4j-based
        cross_links = []
        if hasattr(self._entity_repo, '_driver') or hasattr(self._entity_repo, 'query_cross_taxonomy_links'):
            from clients.neo4j_client import Neo4jClient as NC
            if isinstance(self._entity_repo, NC):
                cross_links = self._entity_repo.query_cross_taxonomy_links(code_a, code_b)

        if code_a == code_b:
            distance, rel_type = 0.0, "SAME"
        elif lca and len(lca) >= 3:
            distance, rel_type = 0.2, "SIBLING"
        elif lca and len(lca) >= 2:
            distance, rel_type = 0.4, "ANCESTOR"
        elif cross_links:
            distance, rel_type = 0.35, "CROSS_TAXONOMY_LINK"
        else:
            distance, rel_type = 0.8, "UNRELATED"

        explanation = self._build_industry_explanation(code_a, code_b, path_a, path_b, lca, cross_links, rel_type)
        return {
            "related": distance < 0.7, "relationship_type": rel_type,
            "path_a": path_a, "path_b": path_b,
            "lowest_common_ancestor": lca, "cross_taxonomy_links": cross_links,
            "semantic_distance": round(distance, 3), "explanation": explanation,
            "duration_ms": int((time.time() - start) * 1000),
        }

    def _build_industry_explanation(self, code_a, code_b, path_a, path_b, lca, cross_links, rel_type) -> str:
        if rel_type == "SAME":
            return f"Same NAICS code: {code_a}"
        if rel_type == "SIBLING":
            return (f"NAICS {code_a} and {code_b} share common ancestor {lca}. "
                    "Same subsector — closely related industries.")
        if rel_type == "CROSS_TAXONOMY_LINK":
            link_desc = ", ".join(l.get("label", l.get("code", "?")) for l in cross_links)
            return (f"Different NAICS sectors ({code_a[:2]} vs {code_b[:2]}) "
                    f"but linked via shared commodity taxonomy: {link_desc}.")
        return f"NAICS {code_a} and {code_b} appear unrelated (no common ancestor or cross-taxonomy links)."

    def _query_commodity_relation(self, code_a: str, code_b: str) -> dict:
        start = time.time()
        prefix_match = min(len(code_a), len(code_b))
        shared = 0
        for i in range(prefix_match):
            if code_a[i] == code_b[i]:
                shared += 1
            else:
                break
        distance = 1.0 - (shared / max(len(code_a), len(code_b), 1))
        return {
            "related": distance < 0.5,
            "relationship_type": "SAME" if distance == 0 else "SIBLING" if distance < 0.3 else "UNRELATED",
            "semantic_distance": round(distance, 3),
            "duration_ms": int((time.time() - start) * 1000),
        }

    def _query_geo_containment(self, geo_a: str, geo_b: str) -> dict:
        start = time.time()
        return {
            "related": geo_a.lower() == geo_b.lower(),
            "relationship_type": "SAME" if geo_a.lower() == geo_b.lower() else "UNRELATED",
            "duration_ms": int((time.time() - start) * 1000),
        }

    def check_shared_context(self, entity_a_id: str, known_counterparties: list[str]) -> dict:
        """Ontology-aware shared neighbor analysis."""
        if not self._entity_repo.available:
            return {"shared_neighbors": [], "industry_coherence": 0.0,
                    "supporting_evidence": "Neo4j unavailable — shared neighbor analysis disabled"}

        a_neighbors = self._rel_repo.get_neighbors(entity_a_id, direction="both")
        a_neighbor_ids = {n.get("id", "") for n in a_neighbors}

        shared = []
        for cp_id in known_counterparties:
            if cp_id in a_neighbor_ids:
                gr_data = self._entity_repo.get(cp_id)
                shared.append({
                    "entity_id": cp_id,
                    "name": gr_data.get("canonical_name", "") if gr_data else "",
                    "industry_naics": gr_data.get("naics_code", "") if gr_data else "",
                })

        coherence = 0.0
        if shared:
            naics_codes = [s.get("industry_naics", "") for s in shared if s.get("industry_naics")]
            if len(naics_codes) >= 2:
                sectors = set(c[:2] for c in naics_codes if len(c) >= 2)
                coherence = 1.0 / max(len(sectors), 1)
            elif len(naics_codes) == 1:
                coherence = 0.5

        evidence = (f"Found {len(shared)} shared transaction partners. "
                    f"Industry coherence: {coherence:.2f}.") if shared else "No shared transaction partners found."
        return {
            "shared_neighbors": shared,
            "industry_coherence": round(coherence, 3),
            "supporting_evidence": evidence,
        }

    def batch_industry_filter(self, reference_naics: str, candidates: list[dict]) -> dict:
        """Check which candidates are related to a reference NAICS code via ontology."""
        matches = []
        for c in candidates:
            code = c.get("naics_code") or ""
            if not code:
                continue
            result = self.query_ontology("INDUSTRY_RELATION", reference_naics, code)
            if result.get("related"):
                matches.append({**c, "relationship": result.get("relationship_type", ""), "explanation": result.get("explanation", "")})
                continue
            result = self.query_ontology("COMMODITY_RELATION", reference_naics, code)
            if result.get("related"):
                matches.append({**c, "relationship": "COMMODITY_LINK", "explanation": f"Shared commodity taxonomy (distance {result.get('semantic_distance', '?')})"})
                continue
            if len(reference_naics) >= 2 and len(code) >= 2 and reference_naics[:2] == code[:2]:
                matches.append({**c, "relationship": "SAME_SECTOR", "explanation": f"Same NAICS sector ({code[:2]})"})
        return {
            "reference_naics": reference_naics, "matches": matches,
            "match_count": len(matches), "unmatched_count": len(candidates) - len(matches),
            "total_candidates": len(candidates),
        }

    def query_network(self, entity_id: str, depth: int = 1, direction: str = "both") -> dict:
        """Multi-hop graph traversal via transaction edges."""
        depth = max(1, min(3, depth))
        if not self._entity_repo.available:
            return {"nodes": [], "edges": [], "depth_reached": 0,
                    "error": "Neo4j unavailable — cannot traverse network"}

        visited = set()
        nodes = []
        edges = []
        frontier = {entity_id}

        for current_depth in range(depth):
            next_frontier = set()
            for eid in frontier:
                if eid in visited:
                    continue
                visited.add(eid)
                neighbors = self._rel_repo.get_neighbors(eid, direction=direction)
                gr_data = self._entity_repo.get(eid)
                node_info = {"entity_id": eid, "canonical_name": gr_data.get("canonical_name", "") if gr_data else "", "depth": current_depth}
                if gr_data:
                    node_info["state"] = gr_data.get("state", "")
                    node_info["naics_code"] = gr_data.get("naics_code", "")
                    node_info["confidence"] = float(gr_data.get("confidence", 0))
                nodes.append(node_info)
                for n in neighbors:
                    neighbor_id = n.get("id", "")
                    if not neighbor_id:
                        continue
                    edges.append({
                        "source": eid, "target": neighbor_id,
                        "relationship": n.get("rel_type", "BUYS_FROM"),
                        "direction": "outgoing" if n.get("is_outgoing") else "incoming",
                        "volume": float(n.get("volume") or 0),
                        "target_name": n.get("name", ""),
                    })
                    if neighbor_id not in visited:
                        next_frontier.add(neighbor_id)
            frontier = next_frontier
            if not frontier:
                break

        for eid in frontier:
            if eid not in visited:
                gr_data = self._entity_repo.get(eid)
                nodes.append({"entity_id": eid, "canonical_name": gr_data.get("canonical_name", "") if gr_data else "",
                              "depth": depth, "state": gr_data.get("state", "") if gr_data else ""})

        return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges),
                "depth_reached": min(depth, len(visited)), "root_entity": entity_id, "source": "neo4j"}

    def find_shortest_path(self, entity_a: str, entity_b: str) -> dict:
        """Find the shortest connection path between two entities."""
        start = time.time()
        if not self._entity_repo.available:
            return {"chain": [], "edges": [], "hops": -1,
                    "error": "Neo4j unavailable", "duration_ms": int((time.time() - start) * 1000)}
        raw = self._rel_repo.find_shortest_path(entity_a, entity_b)
        if raw:
            chain = [{"id": n.get("id", ""), "name": n.get("name", ""), "type": n.get("type", "")} for n in raw.get("chain", [])]
            return {"chain": chain, "edges": raw.get("edges", []), "hops": raw.get("hops", 0),
                    "duration_ms": int((time.time() - start) * 1000)}
        return {"chain": [], "edges": [], "hops": -1, "message": "No path found.",
                "duration_ms": int((time.time() - start) * 1000)}

    def find_common_neighbors(self, entity_a_id: str, entity_b_id: str, limit: int = 20) -> dict:
        start = time.time()
        gr_a = self._entity_repo.get(entity_a_id)
        gr_b = self._entity_repo.get(entity_b_id)
        name_a = gr_a.get("canonical_name", entity_a_id) if gr_a else entity_a_id
        name_b = gr_b.get("canonical_name", entity_b_id) if gr_b else entity_b_id
        if not self._entity_repo.available:
            return {"common_neighbors": [], "count": 0, "entity_a_name": name_a, "entity_b_name": name_b,
                    "error": "Neo4j unavailable", "duration_ms": int((time.time() - start) * 1000)}
        raw = self._rel_repo.find_common_neighbors(entity_a_id, entity_b_id, limit=limit)
        neighbors = [{"id": r.get("id", ""), "name": r.get("name", ""), "naics_code": r.get("naics_code", ""),
                       "rel_to_a": r.get("rel_to_a", ""), "vol_a": float(r.get("vol_a") or 0),
                       "rel_to_b": r.get("rel_to_b", ""), "vol_b": float(r.get("vol_b") or 0)} for r in raw]
        return {"common_neighbors": neighbors, "count": len(neighbors), "entity_a_name": name_a,
                "entity_b_name": name_b, "duration_ms": int((time.time() - start) * 1000)}

    def detect_cluster(self, entity_id: str, max_size: int = 20) -> dict:
        start = time.time()
        if not self._entity_repo.available:
            return {"nodes": [], "edges": [], "density": 0.0, "center": entity_id,
                    "member_count": 0, "top_industries": [], "error": "Neo4j unavailable",
                    "duration_ms": int((time.time() - start) * 1000)}
        gr_center = self._entity_repo.get(entity_id)
        center_name = gr_center.get("canonical_name", entity_id) if gr_center else entity_id
        raw = self._rel_repo.find_cluster(entity_id, max_size=max_size)
        if not raw:
            return {"nodes": [], "edges": [], "density": 0.0, "center": center_name,
                    "member_count": 0, "top_industries": [], "duration_ms": int((time.time() - start) * 1000)}
        nodes = [{"id": n.get("id", ""), "name": n.get("name", ""), "naics_code": n.get("naics_code", "")} for n in raw.get("nodes", [])]
        nodes.insert(0, {"id": entity_id, "name": center_name, "naics_code": gr_center.get("naics_code", "") if gr_center else "",
                         "state": gr_center.get("state", "") if gr_center else "", "is_center": True})
        naics_counts = {}
        for n in nodes:
            code = n.get("naics_code", "")
            if code:
                sector = code[:4] if len(code) >= 4 else code
                naics_counts[sector] = naics_counts.get(sector, 0) + 1
        top_industries = sorted(naics_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        return {"nodes": nodes, "edges": raw.get("edges", []), "density": raw.get("density", 0.0),
                "center": center_name, "member_count": len(nodes),
                "top_industries": [{"naics": k, "count": v} for k, v in top_industries],
                "duration_ms": int((time.time() - start) * 1000)}

    def assess_risk_impact(self, entity_id: str, max_depth: int = 3) -> dict:
        start = time.time()
        if not self._entity_repo.available:
            return {"affected_entities": [], "affected_count": 0, "total_volume_at_risk": 0,
                    "depth_distribution": {}, "error": "Neo4j unavailable",
                    "duration_ms": int((time.time() - start) * 1000)}
        gr_target = self._entity_repo.get(entity_id)
        target_name = gr_target.get("canonical_name", entity_id) if gr_target else entity_id
        raw = self._rel_repo.assess_impact(entity_id, max_depth=max_depth)
        if not raw:
            return {"target_entity": target_name, "affected_entities": [], "affected_count": 0,
                    "total_volume_at_risk": 0, "depth_distribution": {},
                    "duration_ms": int((time.time() - start) * 1000)}
        affected = [{"id": a.get("id", ""), "name": a.get("name", ""), "depth": a.get("depth", 1),
                      "volume_at_risk": float(a.get("volume_at_risk", 0))} for a in raw.get("affected", [])]
        total_vol = raw.get("total_volume_at_risk", 0)
        depth_dist = raw.get("depth_distribution", {})
        concentration = self._concentration_warning(affected, total_vol)
        return {"target_entity": target_name, "affected_entities": affected, "affected_count": len(affected),
                "total_volume_at_risk": total_vol, "depth_distribution": depth_dist,
                "concentration_warning": concentration, "duration_ms": int((time.time() - start) * 1000)}

    def _concentration_warning(self, affected: list[dict], total_volume: float):
        if not affected or total_volume <= 0:
            return None
        depth_1 = [a for a in affected if a.get("depth") == 1]
        for a in depth_1:
            vol = a.get("volume_at_risk", 0)
            if vol > total_volume * 0.5:
                return f"{a.get('name', a.get('id', '?'))} accounts for {vol / total_volume * 100:.0f}% of at-risk volume"
        return None

    async def traverse_supply_chain(
        self, start_entity_id: str, hops: list[str],
        max_per_hop: int = 5, min_volume: float = 0,
    ) -> dict:
        """Directed multi-hop supply chain traversal."""
        start = time.time()
        valid_hops = {"vendor", "client", "customer"}
        for h in hops:
            if h not in valid_hops:
                return {"error": f"Invalid hop direction: '{h}'. Use 'vendor' or 'client'."}
        if len(hops) > 5:
            return {"error": "Maximum 5 hops supported."}
        if not self._entity_repo.available:
            return {"error": "Neo4j unavailable", "paths": [], "total_paths": 0}

        from clients.redis_client import RedisClient
        cache_key = RedisClient.traverse_key(start_entity_id, hops)
        cached = await self._cache.get_cached(cache_key)
        if cached:
            cached["from_cache"] = True
            cached["duration_ms"] = int((time.time() - start) * 1000)
            return cached

        raw_paths = self._rel_repo.traverse_supply_chain(
            start_id=start_entity_id, hops=hops,
            max_per_hop=max_per_hop, min_volume=min_volume,
        )
        paths = []
        for rp in raw_paths:
            chain = [{"id": node.get("id", ""), "name": node.get("name", ""), "hop": i, "type": node.get("type", "")}
                     for i, node in enumerate(rp.get("chain", []))]
            edges_out = [{"from": chain[j]["id"] if j < len(chain) else "",
                          "to": chain[j + 1]["id"] if j + 1 < len(chain) else "",
                          "type": edge.get("type", ""), "volume": float(edge.get("volume") or 0)}
                         for j, edge in enumerate(rp.get("edges", []))]
            paths.append({"chain": chain, "edges": edges_out, "total_volume": float(rp.get("total_volume", 0))})

        all_nodes = {}
        for p in paths:
            for node in p.get("chain", []):
                nid = node.get("id", "")
                if nid and nid not in all_nodes:
                    all_nodes[nid] = node

        insights = self._compute_insights(paths, start_entity_id)
        result = {"paths": paths, "total_paths": len(paths), "nodes": list(all_nodes.values()),
                  "insights": insights, "depth": len(hops),
                  "duration_ms": int((time.time() - start) * 1000), "from_cache": False}
        await self._cache.set_cached(cache_key, result)
        return result

    def _compute_insights(self, paths, start_id):
        if not paths:
            return {"shared_entities": [], "circular_paths": [], "concentration_risk": 0.0}
        entity_hops = {}
        for p in paths:
            for node in p.get("chain", []):
                nid = node.get("id", "")
                hop = node.get("hop", 0)
                if nid:
                    entity_hops.setdefault(nid, set()).add(hop)
        shared = [{"id": eid, "hops": sorted(h)} for eid, h in entity_hops.items() if len(h) > 1 and eid != start_id]
        circular = [i for i, p in enumerate(paths) if p.get("chain") and p["chain"][-1].get("id") == start_id]
        hop1_volumes = {}
        for p in paths:
            if len(p.get("edges", [])) >= 1:
                edge = p["edges"][0]
                target = edge.get("to", "")
                hop1_volumes[target] = hop1_volumes.get(target, 0) + edge.get("volume", 0)
        total_vol = sum(hop1_volumes.values())
        max_vol = max(hop1_volumes.values()) if hop1_volumes else 0
        concentration = round(max_vol / total_vol, 3) if total_vol > 0 else 0.0
        return {"shared_entities": shared, "circular_paths": circular, "concentration_risk": concentration}
