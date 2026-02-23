"""
GraphDB SPARQL client — connects to Ontotext GraphDB Free.

T-Box reads (ontology): query_ontology, check_shared_context
A-Box writes: write_entity_triples, write_merge_redirect

Includes T-Box query cache (static ontology — safe to cache for hours).
Falls back to no-op if GraphDB unavailable.
"""
from __future__ import annotations
import logging
import time
from typing import Optional
from functools import lru_cache
from config import KnowledgeGraphConfig

logger = logging.getLogger(__name__)

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


class GraphDBClient:
    def __init__(self, cfg: KnowledgeGraphConfig):
        self._cfg = cfg
        self._client: Optional[httpx.Client] = None
        self._available = False
        self._cache: dict[str, tuple[float, dict]] = {}
        self._cache_ttl = cfg.t_box_cache_ttl_hours * 3600

    async def connect(self):
        if not HAS_HTTPX:
            logger.warning("httpx not installed — GraphDB unavailable")
            return
        try:
            self._client = httpx.Client(timeout=self._cfg.timeout_ms / 1000)
            # Health check
            resp = self._client.get(
                self._cfg.sparql_endpoint,
                params={"query": "ASK { ?s ?p ?o }"},
                headers={"Accept": "application/sparql-results+json"},
            )
            if resp.status_code == 200:
                self._available = True
                logger.info(f"GraphDB connected: {self._cfg.sparql_endpoint}")
            else:
                logger.warning(f"GraphDB returned {resp.status_code}")
        except Exception as e:
            logger.warning(f"GraphDB unavailable ({e}) — ontology queries disabled")

    @property
    def available(self) -> bool:
        return self._available

    # ── SPARQL SELECT ───────────────────────────────────────

    def query(self, sparql: str, use_cache: bool = False) -> list[dict]:
        """Execute SPARQL SELECT. Returns list of binding dicts."""
        if not self._available:
            return []

        # Cache check for T-Box queries
        if use_cache:
            cached = self._cache.get(sparql)
            if cached and (time.time() - cached[0]) < self._cache_ttl:
                return cached[1]["results"]

        try:
            resp = self._client.get(
                self._cfg.sparql_endpoint,
                params={"query": sparql},
                headers={"Accept": "application/sparql-results+json"},
            )
            resp.raise_for_status()
            data = resp.json()
            bindings = data.get("results", {}).get("bindings", [])
            results = []
            for b in bindings:
                row = {}
                for var, val in b.items():
                    row[var] = val.get("value", "")
                results.append(row)

            if use_cache:
                self._cache[sparql] = (time.time(), {"results": results})

            return results
        except Exception as e:
            logger.error(f"SPARQL query failed: {e}")
            return []

    # ── SPARQL UPDATE ───────────────────────────────────────

    def update(self, sparql: str) -> bool:
        """Execute SPARQL UPDATE (INSERT/DELETE). Returns success."""
        if not self._available:
            logger.warning("GraphDB unavailable — skipping update")
            return False
        try:
            resp = self._client.post(
                self._cfg.update_endpoint,
                data=sparql,
                headers={"Content-Type": "application/sparql-update"},
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"SPARQL update failed: {e}")
            logger.debug(f"Failing SPARQL:\n{sparql}")
            return False

    # ── High-level ontology queries (T-Box, cached) ─────────

    def query_naics_hierarchy(self, naics_code: str) -> list[str]:
        """Walk NAICS hierarchy upward. Returns ancestor codes."""
        sparql = f"""
        PREFIX naics: <http://qb.intuit.com/ontology/naics/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX qb: <http://qb.intuit.com/ontology/>

        SELECT ?ancestor WHERE {{
            naics:{naics_code} rdfs:subClassOf* ?ancestor .
            ?ancestor a qb:NAICSCode .
        }}
        """
        rows = self.query(sparql, use_cache=True)
        return [r["ancestor"].split("/")[-1] for r in rows]

    def query_lowest_common_ancestor(self, code_a: str, code_b: str) -> Optional[str]:
        """Find LCA of two NAICS codes. Returns code or None."""
        sparql = f"""
        PREFIX naics: <http://qb.intuit.com/ontology/naics/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX qb: <http://qb.intuit.com/ontology/>

        SELECT ?lca WHERE {{
            naics:{code_a} rdfs:subClassOf* ?lca .
            naics:{code_b} rdfs:subClassOf* ?lca .
            ?lca a qb:NAICSCode .
        }} ORDER BY DESC(STRLEN(STR(?lca))) LIMIT 1
        """
        rows = self.query(sparql, use_cache=True)
        if rows:
            return rows[0]["lca"].split("/")[-1]
        return None

    def query_cross_taxonomy_links(self, code_a: str, code_b: str) -> list[dict]:
        """Find shared commodity links between NAICS codes via skos:related."""
        sparql = f"""
        PREFIX naics: <http://qb.intuit.com/ontology/naics/>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

        SELECT ?link ?label WHERE {{
            naics:{code_a} skos:related ?link .
            naics:{code_b} skos:related ?link .
            ?link rdfs:label ?label .
        }}
        """
        rows = self.query(sparql, use_cache=True)
        return [{"code": r["link"].split("/")[-1], "label": r["label"]} for r in rows]

    def query_shared_neighbors(self, entity_id: str) -> list[dict]:
        """Get entity's transaction partners with names and NAICS."""
        sparql = f"""
        PREFIX entity: <http://qb.intuit.com/entity/>
        PREFIX qb: <http://qb.intuit.com/ontology/>

        SELECT ?neighbor ?name ?naics WHERE {{
            entity:{entity_id} qb:transactsWith ?neighbor .
            ?neighbor qb:canonicalName ?name .
            OPTIONAL {{ ?neighbor qb:operatesIn ?naicsNode . BIND(STRAFTER(STR(?naicsNode), "naics/") AS ?naics) }}
        }}
        """
        return self.query(sparql)

    # ── A-Box writes ────────────────────────────────────────

    def create_entity_triples(self, entity_id: str, attrs: dict) -> int:
        """Write A-Box triples for a new or updated entity. Returns triple count.

        Uses DELETE/INSERT to avoid stacking duplicate triples on updates.
        Preserves rdf:type and relationship triples (qb:transactsWith).
        """
        pfx = """
        PREFIX entity: <http://qb.intuit.com/entity/>
        PREFIX qb: <http://qb.intuit.com/ontology/>
        PREFIX naics: <http://qb.intuit.com/ontology/naics/>
        PREFIX unspsc: <http://qb.intuit.com/ontology/unspsc/>
        PREFIX geo: <http://qb.intuit.com/ontology/geo/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        """

        # Step 1: Delete old attribute triples (keep rdf:type and transactsWith)
        delete_sparql = f"""{pfx}
        DELETE {{ entity:{entity_id} ?p ?o }}
        WHERE  {{
            entity:{entity_id} ?p ?o .
            FILTER(?p != rdf:type && ?p != qb:transactsWith)
        }}
        """
        self.update(delete_sparql)

        # Step 2: Build fresh triples
        entity_type = _iri_safe(attrs.get("entity_type", "Phantom")) or "Phantom"
        triples = [
            f'entity:{entity_id} rdf:type qb:Business .',
            f'entity:{entity_id} qb:canonicalName "{_esc(attrs.get("canonical_name", ""))}" .',
            f'entity:{entity_id} qb:entityType qb:{entity_type} .',
            f'entity:{entity_id} qb:confidence "{attrs.get("confidence", 0.5)}"^^xsd:float .',
        ]

        # Classification links to T-Box
        for naics in attrs.get("naics_codes", []):
            if naics:
                triples.append(f'entity:{entity_id} qb:operatesIn naics:{naics} .')
        for unspsc in attrs.get("unspsc_codes", []):
            if unspsc:
                triples.append(f'entity:{entity_id} qb:provides unspsc:{unspsc} .')
        geo = attrs.get("geo_location", "")
        if geo:
            geo_safe = _iri_safe(geo)
            if geo_safe:
                triples.append(f'entity:{entity_id} qb:locatedIn geo:{geo_safe} .')
        for variant in attrs.get("name_variants", []):
            if variant:
                triples.append(f'entity:{entity_id} qb:nameVariant "{_esc(variant)}" .')

        # Optional identity properties
        for prop, pred in [
            ("ein", "qb:ein"), ("email", "qb:email"), ("phone", "qb:phone"),
            ("contact_name", "qb:contactName"), ("street_address", "qb:streetAddress"),
            ("zip_code", "qb:zipCode"), ("payment_terms", "qb:paymentTerms"),
        ]:
            if attrs.get(prop):
                triples.append(f'entity:{entity_id} {pred} "{_esc(attrs[prop])}" .')

        # Step 3: Insert fresh triples
        insert_sparql = f"""{pfx}
        INSERT DATA {{
            {chr(10).join('    ' + t for t in triples)}
        }}
        """
        success = self.update(insert_sparql)
        return len(triples) if success else 0

    def write_merge_redirect(
        self, survivor_id: str, absorbed_id: str, survivor_updates: dict
    ) -> dict:
        """Handle KG updates for golden-to-golden merge.

        CRITICAL: owl:sameAs must be LAST — causes inferred inheritance.
        Order: migrate edges → update survivor → delete absorbed attrs → sameAs.
        """
        results = {"triples_migrated": 0, "triples_created": 0,
                    "triples_deleted": 0, "redirect_created": False}

        pfx = """
        PREFIX entity: <http://qb.intuit.com/entity/>
        PREFIX qb: <http://qb.intuit.com/ontology/>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX naics: <http://qb.intuit.com/ontology/naics/>
        PREFIX unspsc: <http://qb.intuit.com/ontology/unspsc/>
        """

        # 1. Migrate relationship triples
        q1 = f"""{pfx}
        DELETE {{ ?x qb:transactsWith entity:{absorbed_id} }}
        INSERT {{ ?x qb:transactsWith entity:{survivor_id} }}
        WHERE  {{ ?x qb:transactsWith entity:{absorbed_id} }}
        """
        if self.update(q1):
            results["triples_migrated"] += 1

        # 2. Update survivor attributes
        new_triples = []
        for variant in survivor_updates.get("name_variants", []):
            new_triples.append(
                f'entity:{survivor_id} qb:nameVariant "{_esc(variant)}" .')
        for code in survivor_updates.get("unspsc_codes", []):
            if code:
                new_triples.append(
                    f'entity:{survivor_id} qb:provides unspsc:{code} .')
        if new_triples:
            q2 = f"""{pfx}\nINSERT DATA {{ {chr(10).join(new_triples)} }}"""
            if self.update(q2):
                results["triples_created"] = len(new_triples)

        # 3. Remove absorbed entity's attribute triples (BEFORE sameAs!)
        q3 = f"""{pfx}
        DELETE {{ entity:{absorbed_id} ?p ?o }}
        WHERE  {{ entity:{absorbed_id} ?p ?o .
                   FILTER(?p != rdf:type) }}
        """
        if self.update(q3):
            results["triples_deleted"] += 1

        # 4. Add redirect LAST — after all explicit triples cleaned
        q4 = f"""{pfx}
        INSERT DATA {{
            entity:{absorbed_id} owl:sameAs entity:{survivor_id} .
            entity:{absorbed_id} qb:entityStatus "MERGED" .
        }}
        """
        results["redirect_created"] = self.update(q4)

        return results

    def create_edge_triple(self, source_id: str, target_id: str, volume: float) -> bool:
        sparql = f"""
        PREFIX entity: <http://qb.intuit.com/entity/>
        PREFIX qb: <http://qb.intuit.com/ontology/>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

        INSERT DATA {{
            entity:{source_id} qb:transactsWith entity:{target_id} .
            entity:{source_id} qb:volume "{volume}"^^xsd:decimal .
        }}
        """
        return self.update(sparql)


def _esc(s: str) -> str:
    """Escape for SPARQL string literals."""
    return (s.replace("\\", "\\\\")
             .replace('"', '\\"')
             .replace("\n", "\\n")
             .replace("\r", "\\r")
             .replace("\t", "\\t")
             .replace("'", "\\'"))


def _iri_safe(s: str) -> str:
    """Convert a string to a safe SPARQL local name (no spaces/special chars)."""
    import re
    return re.sub(r'[^A-Za-z0-9_-]', '_', s.strip())
