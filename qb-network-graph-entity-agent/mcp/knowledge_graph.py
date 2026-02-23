"""
MCP Server 2: knowledge_graph — Ontology reasoning + KG Store R/W.

4 tools:
  query_ontology         — T-Box semantic relationship queries (cached)
  check_shared_context   — A-Box shared neighbor analysis
  write_entity_triples   — A-Box create/update entity
  write_merge_redirect   — A-Box golden-to-golden merge

Connected store: GraphDB Free (SPARQL 1.1 endpoint)
Design doc §2.2.
"""
from __future__ import annotations
import logging
import time
from typing import Optional
from clients.graphdb_client import GraphDBClient

logger = logging.getLogger(__name__)


class KnowledgeGraphServer:
    """MCP Server 2: knowledge_graph — ontology reasoning + KG writes."""

    def __init__(self, graphdb: GraphDBClient):
        self._gdb = graphdb

    @property
    def available(self) -> bool:
        return self._gdb.available

    # ── Tool 1: query_ontology ──────────────────────────────

    def query_ontology(
        self,
        query_type: str,        # INDUSTRY_RELATION | COMMODITY_RELATION | GEO_CONTAINMENT
        code_a: str = "",
        code_b: str = "",
    ) -> dict:
        """Query T-Box ontology for semantic relationships.

        Used by compare_fields when NAICS sectors differ.
        Finds cross-taxonomy links (e.g., plumbing wholesaler ↔ contractor
        connected via shared UNSPSC commodity).

        Returns:
            related: bool
            relationship_type: str
            cross_taxonomy_links: list
            semantic_distance: float (0=identical, 1=unrelated)
            explanation: str
        """
        start = time.time()

        if not self._gdb.available:
            return self._fallback_ontology(code_a, code_b)

        if query_type == "INDUSTRY_RELATION":
            return self._query_industry_relation(code_a, code_b, start)
        elif query_type == "COMMODITY_RELATION":
            return self._query_commodity_relation(code_a, code_b, start)
        elif query_type == "GEO_CONTAINMENT":
            return self._query_geo_containment(code_a, code_b, start)
        else:
            return {"error": f"Unknown query_type: {query_type}"}

    def _query_industry_relation(self, code_a: str, code_b: str, start: float) -> dict:
        # Walk hierarchies
        path_a = self._gdb.query_naics_hierarchy(code_a)
        path_b = self._gdb.query_naics_hierarchy(code_b)

        # Find LCA
        lca = self._gdb.query_lowest_common_ancestor(code_a, code_b)

        # Check cross-taxonomy links
        cross_links = self._gdb.query_cross_taxonomy_links(code_a, code_b)

        # Compute semantic distance
        if code_a == code_b:
            distance = 0.0
            rel_type = "SAME"
        elif lca and len(lca) >= 3:
            distance = 0.2
            rel_type = "SIBLING"
        elif lca and len(lca) >= 2:
            distance = 0.4
            rel_type = "ANCESTOR"
        elif cross_links:
            distance = 0.35
            rel_type = "CROSS_TAXONOMY_LINK"
        else:
            distance = 0.8
            rel_type = "UNRELATED"

        # Build explanation
        explanation = self._build_industry_explanation(
            code_a, code_b, path_a, path_b, lca, cross_links, rel_type
        )

        elapsed = int((time.time() - start) * 1000)
        return {
            "related": distance < 0.7,
            "relationship_type": rel_type,
            "path_a": path_a,
            "path_b": path_b,
            "lowest_common_ancestor": lca,
            "cross_taxonomy_links": cross_links,
            "semantic_distance": round(distance, 3),
            "explanation": explanation,
            "duration_ms": elapsed,
        }

    def _build_industry_explanation(
        self, code_a, code_b, path_a, path_b, lca, cross_links, rel_type
    ) -> str:
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

    def _query_commodity_relation(self, code_a: str, code_b: str, start: float) -> dict:
        # Simplified — check if codes share a parent
        # In production, walk UNSPSC hierarchy
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

    def _query_geo_containment(self, geo_a: str, geo_b: str, start: float) -> dict:
        # Simplified geo containment
        return {
            "related": geo_a.lower() == geo_b.lower(),
            "relationship_type": "SAME" if geo_a.lower() == geo_b.lower() else "UNRELATED",
            "duration_ms": int((time.time() - start) * 1000),
        }

    def _fallback_ontology(self, code_a: str, code_b: str) -> dict:
        """Fallback when GraphDB is unavailable — conservative string prefix matching."""
        if not code_a or not code_b:
            return {"related": False, "relationship_type": "UNRELATED",
                    "semantic_distance": 1.0, "cross_taxonomy_links": [],
                    "explanation": "Ontology unavailable, codes missing"}
        # Simple prefix check
        shared_prefix = 0
        for a, b in zip(code_a, code_b):
            if a == b:
                shared_prefix += 1
            else:
                break

        if shared_prefix >= 4:
            return {"related": True, "relationship_type": "SIBLING",
                    "semantic_distance": 0.2, "cross_taxonomy_links": [],
                    "explanation": f"Prefix match ({shared_prefix} digits) — likely related"}
        elif shared_prefix >= 2:
            return {"related": True, "relationship_type": "ANCESTOR",
                    "semantic_distance": 0.5, "cross_taxonomy_links": [],
                    "explanation": f"Same sector ({code_a[:2]}) — possibly related"}
        else:
            return {"related": False, "relationship_type": "UNRELATED",
                    "semantic_distance": 0.8, "cross_taxonomy_links": [],
                    "explanation": "Different sectors, no ontology available"}

    # ── Tool 2: check_shared_context ────────────────────────

    def check_shared_context(
        self,
        entity_a_id: str,
        known_counterparties: list[str],
    ) -> dict:
        """Ontology-aware shared neighbor analysis.

        Checks if candidate (entity_a) and orphan's known counterparties
        share transaction partners, and whether they form a coherent
        industry cluster.
        """
        if not self._gdb.available:
            return {"shared_neighbors": [], "industry_coherence": 0.0,
                    "supporting_evidence": "GraphDB unavailable"}

        # Get A's neighbors from KG
        a_neighbors = self._gdb.query_shared_neighbors(entity_a_id)
        a_neighbor_ids = {n.get("neighbor", "").split("/")[-1] for n in a_neighbors}

        # Find intersection with orphan's known counterparties
        shared = []
        for cp_id in known_counterparties:
            if cp_id in a_neighbor_ids:
                # Find the matching neighbor record
                for n in a_neighbors:
                    if n.get("neighbor", "").split("/")[-1] == cp_id:
                        shared.append({
                            "entity_id": cp_id,
                            "name": n.get("name", ""),
                            "industry_naics": n.get("naics", ""),
                        })

        # Industry coherence — do shared neighbors cluster in related industries?
        coherence = 0.0
        if shared:
            naics_codes = [s.get("industry_naics", "") for s in shared if s.get("industry_naics")]
            if len(naics_codes) >= 2:
                # Check if they share sector/subsector
                sectors = set(c[:2] for c in naics_codes if len(c) >= 2)
                coherence = 1.0 / max(len(sectors), 1)  # Fewer distinct sectors = higher coherence
            elif len(naics_codes) == 1:
                coherence = 0.5

        evidence = (
            f"Found {len(shared)} shared transaction partners. "
            f"Industry coherence: {coherence:.2f}."
        ) if shared else "No shared transaction partners found."

        return {
            "shared_neighbors": shared,
            "industry_coherence": round(coherence, 3),
            "supporting_evidence": evidence,
        }

    # ── Tool 3: write_entity_triples ────────────────────────

    def write_entity_triples(
        self,
        entity_id: str,
        attrs: dict,
    ) -> dict:
        """Write A-Box triples for entity lifecycle events (create/update).

        Falls back to changelog sync if GraphDB unavailable.
        """
        if not self._gdb.available:
            logger.warning(f"GraphDB unavailable — falling back to changelog for {entity_id}")
            return {"success": False, "triples_written": 0, "fallback_to_changelog": True}

        count = self._gdb.create_entity_triples(entity_id, attrs)
        return {
            "success": count > 0,
            "triples_written": count,
            "fallback_to_changelog": False,
        }

    # ── Tool 4: write_merge_redirect ────────────────────────

    def write_merge_redirect(
        self,
        survivor_id: str,
        absorbed_id: str,
        survivor_updates: dict,
    ) -> dict:
        """Handle KG updates for golden-to-golden merges.

        CRITICAL: owl:sameAs must be LAST — causes inferred inheritance.
        """
        if not self._gdb.available:
            logger.warning(f"GraphDB unavailable — merge redirect deferred for {absorbed_id} → {survivor_id}")
            return {"success": False, "fallback_to_changelog": True,
                    "triples_migrated": 0, "redirect_created": False}

        result = self._gdb.write_merge_redirect(survivor_id, absorbed_id, survivor_updates)
        result["success"] = result.get("redirect_created", False)
        result["fallback_to_changelog"] = False
        return result
