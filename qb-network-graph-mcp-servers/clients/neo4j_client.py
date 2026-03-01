"""
Neo4j client — primary golden record store + directed graph traversal + T-Box taxonomy.

A-Box (instance data):
  Entity nodes store the full golden record (30+ properties).
  Write methods are the primary persistence path (Neo4j IS the source of truth).
  Read methods provide point lookups, bucket-key search, name search,
  aggregation, audit trail, and multi-hop directed traversal.

T-Box (ontology / taxonomy):
  NAICS hierarchy computed from code structure (pure Python, no DB needed).
  Cross-taxonomy commodity links stored as NAICSCode → COMMODITY_LINK edges.
  Seeded on connect with common construction/trade sector cross-links.

Falls back gracefully if Neo4j is unavailable (same pattern as former GraphDBClient).
"""
from __future__ import annotations
import json
import logging
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

# Direction mapping: hop name → Cypher relationship pattern
_HOP_PATTERNS = {
    "vendor": "-[:BUYS_FROM]->",
    "client": "-[:SELLS_TO]->",
    "customer": "-[:SELLS_TO]->",
}


class Neo4jClient:
    def __init__(self, cfg: Neo4jConfig):
        self._cfg = cfg
        self._driver = None
        self._available = False
        self._using_mock = False

        # In-memory mock storage (for tests)
        self._mock_entities: dict[str, dict] = {}
        self._mock_audit: list[dict] = []
        self._mock_relationships: dict[str, dict] = {}

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

            # Ensure schema constraints
            self._ensure_schema()
        except Exception as e:
            logger.warning(f"Neo4j unavailable ({e}) — graph traversal disabled")

    def _ensure_schema(self):
        """Create constraints and indexes if they don't exist."""
        queries = [
            # Primary key + existing indexes
            "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
            "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.canonical_name)",
            "CREATE INDEX entity_status IF NOT EXISTS FOR (e:Entity) ON (e.status)",
            "CREATE CONSTRAINT naics_code IF NOT EXISTS FOR (n:NAICSCode) REQUIRE n.code IS UNIQUE",
            # Bucket-key equivalent indexes for candidate search
            "CREATE INDEX entity_ein IF NOT EXISTS FOR (e:Entity) ON (e.ein)",
            "CREATE INDEX entity_phone IF NOT EXISTS FOR (e:Entity) ON (e.phone_digits)",
            "CREATE INDEX entity_email_domain IF NOT EXISTS FOR (e:Entity) ON (e.email_domain)",
            "CREATE INDEX entity_naics_state IF NOT EXISTS FOR (e:Entity) ON (e.naics_code, e.state)",
            "CREATE INDEX entity_naics_sub_state IF NOT EXISTS FOR (e:Entity) ON (e.naics_subsector, e.state)",
            "CREATE INDEX entity_zip3 IF NOT EXISTS FOR (e:Entity) ON (e.zip3)",
            "CREATE INDEX entity_city_state IF NOT EXISTS FOR (e:Entity) ON (e.city, e.state)",
            "CREATE FULLTEXT INDEX entity_name_ft IF NOT EXISTS FOR (e:Entity) ON EACH [e.canonical_name]",
            # Audit trail
            "CREATE CONSTRAINT audit_id IF NOT EXISTS FOR (a:AuditEntry) REQUIRE a.audit_id IS UNIQUE",
            "CREATE INDEX audit_entity IF NOT EXISTS FOR (a:AuditEntry) ON (a.target_golden_id)",
        ]
        with self._driver.session(database=self._cfg.database) as session:
            for q in queries:
                try:
                    session.run(q)
                except Exception as e:
                    logger.debug(f"Schema query skipped ({e}): {q}")
        self._seed_cross_taxonomy_links()

    async def close(self):
        if self._driver:
            self._driver.close()
            logger.info("Neo4j driver closed")

    @property
    def available(self) -> bool:
        return self._available

    # ── Write methods (primary store) ─────────────────────────

    def upsert_entity(self, gr: dict):
        """Create or update an Entity node from a golden record dict (30+ properties)."""
        if self._using_mock:
            params = self._gr_to_params(gr)
            self._mock_entities[params["id"]] = params
            return
        if not self._available:
            return
        cypher = """
        MERGE (e:Entity {id: $id})
        ON CREATE SET e.created_at = datetime()
        SET e.canonical_name = $canonical_name,
            e.entity_type = $entity_type,
            e.status = $status,
            e.confidence = $confidence,
            e.source_count = $source_count,
            e.ein = $ein,
            e.phone_digits = $phone_digits,
            e.email = $email,
            e.email_domain = $email_domain,
            e.contact_name = $contact_name,
            e.naics_code = $naics_code,
            e.naics_sector = $naics_sector,
            e.naics_subsector = $naics_subsector,
            e.state = $state,
            e.city = $city,
            e.zip5 = $zip5,
            e.zip3 = $zip3,
            e.street_address = $street_address,
            e.total_volume = $total_volume,
            e.avg_transaction = $avg_transaction,
            e.transaction_count = $transaction_count,
            e.volume_bracket = $volume_bracket,
            e.merged_into = $merged_into,
            e.name_variants = $name_variants,
            e.commodity_keywords = $commodity_keywords,
            e.service_categories = $service_categories,
            e.bucket_keys = $bucket_keys,
            e.source_records = $source_records,
            e.persona = $persona,
            e.updated_at = datetime()
        """
        params = self._gr_to_params(gr)
        try:
            with self._driver.session(database=self._cfg.database) as session:
                session.run(cypher, params)
        except Exception as e:
            logger.error(f"Neo4j upsert_entity failed: {e}")

    def _gr_to_params(self, gr: dict) -> dict:
        """Extract Neo4j parameters from a golden record dict, resolving persona."""
        persona = gr.get("persona", {})
        if isinstance(persona, str):
            try:
                persona = json.loads(persona)
            except Exception:
                persona = {}
        # If persona is a Pydantic model, convert to dict
        if hasattr(persona, 'model_dump'):
            persona = persona.model_dump()

        identity = persona.get("identity", {}) if isinstance(persona, dict) else {}
        industry = persona.get("industry", {}) if isinstance(persona, dict) else {}
        location = persona.get("location", {}) if isinstance(persona, dict) else {}
        behavioral = persona.get("behavioral", {}) if isinstance(persona, dict) else {}
        commodity = persona.get("commodity", {}) if isinstance(persona, dict) else {}

        def _list_val(val):
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return [val] if val else []
            return val if isinstance(val, list) else []

        return {
            "id": gr.get("golden_record_id", ""),
            "canonical_name": gr.get("canonical_name", ""),
            "entity_type": gr.get("entity_type", "PHANTOM"),
            "status": gr.get("status", "ACTIVE"),
            "confidence": float(gr.get("confidence", 0.5)),
            "source_count": int(gr.get("source_count", 1)),
            "ein": gr.get("ein") or identity.get("ein_clean"),
            "phone_digits": gr.get("phone_digits") or identity.get("phone_digits"),
            "email": gr.get("email") or identity.get("email"),
            "email_domain": gr.get("email_domain") or identity.get("email_domain"),
            "contact_name": gr.get("contact_name"),
            "naics_code": gr.get("naics_code") or industry.get("naics_code", ""),
            "naics_sector": gr.get("naics_sector") or industry.get("naics_sector"),
            "naics_subsector": gr.get("naics_subsector") or industry.get("naics_subsector"),
            "state": gr.get("state") or location.get("state", ""),
            "city": gr.get("city") or location.get("city_norm", ""),
            "zip5": gr.get("zip5") or location.get("zip5"),
            "zip3": gr.get("zip3") or location.get("zip3"),
            "street_address": gr.get("street_address"),
            "total_volume": float(gr["total_volume"]) if gr.get("total_volume") is not None else None,
            "avg_transaction": float(gr["avg_transaction"]) if gr.get("avg_transaction") is not None else (
                float(behavioral.get("avg_transaction")) if behavioral.get("avg_transaction") is not None else None),
            "transaction_count": int(gr["transaction_count"]) if gr.get("transaction_count") is not None else (
                int(behavioral.get("transaction_count")) if behavioral.get("transaction_count") is not None else None),
            "volume_bracket": gr.get("volume_bracket") or behavioral.get("volume_bracket"),
            "merged_into": gr.get("merged_into"),
            "name_variants": _list_val(gr.get("name_variants", [])),
            "commodity_keywords": _list_val(gr.get("commodity_keywords")) or commodity.get("top_keywords", []),
            "service_categories": _list_val(gr.get("service_categories")) or commodity.get("service_categories", []),
            "bucket_keys": _list_val(gr.get("bucket_keys", [])),
            "source_records": _list_val(gr.get("source_records", [])),
            "persona": json.dumps(persona, default=str) if persona else "{}",
        }

    def create_relationship(
        self, source_id: str, target_id: str, rel_type: str, properties: dict = None,
    ):
        """Create a directed relationship between two Entity nodes.

        rel_type: 'BUYS_FROM' or 'SELLS_TO'.
        """
        if self._using_mock:
            props = properties or {}
            edge_id = props.get("edge_id", self.generate_id("E"))
            self._mock_relationships[edge_id] = {
                "edge_id": edge_id,
                "source_entity_id": source_id,
                "target_entity_id": target_id,
                "rel_type": rel_type,
                "volume": props.get("volume"),
                "count": props.get("count"),
            }
            return
        if not self._available:
            return
        props = properties or {}
        cypher = f"""
        MERGE (s:Entity {{id: $source_id}})
        MERGE (t:Entity {{id: $target_id}})
        MERGE (s)-[r:{rel_type}]->(t)
        SET r.volume = $volume,
            r.count = $count,
            r.edge_id = $edge_id,
            r.updated_at = datetime()
        """
        params = {
            "source_id": source_id,
            "target_id": target_id,
            "volume": float(props.get("volume") or 0),
            "count": int(props.get("count") or 0),
            "edge_id": props.get("edge_id", ""),
        }
        try:
            with self._driver.session(database=self._cfg.database) as session:
                session.run(cypher, params)
        except Exception as e:
            logger.error(f"Neo4j create_relationship failed: {e}")

    def merge_entities(self, survivor_id: str, absorbed_id: str):
        """Migrate all edges from absorbed to survivor, then mark absorbed as MERGED."""
        if self._using_mock:
            if absorbed_id in self._mock_entities:
                self._mock_entities[absorbed_id]["status"] = "MERGED"
                self._mock_entities[absorbed_id]["merged_into"] = survivor_id
            return
        if not self._available:
            return
        cypher = """
        // Migrate incoming BUYS_FROM edges
        MATCH (x:Entity)-[r:BUYS_FROM]->(absorbed:Entity {id: $absorbed_id})
        WHERE x.id <> $survivor_id
        MERGE (survivor:Entity {id: $survivor_id})
        MERGE (x)-[nr:BUYS_FROM]->(survivor)
        SET nr.volume = coalesce(nr.volume, 0) + coalesce(r.volume, 0),
            nr.count = coalesce(nr.count, 0) + coalesce(r.count, 0),
            nr.updated_at = datetime()
        DELETE r
        """
        cypher2 = """
        // Migrate outgoing BUYS_FROM edges
        MATCH (absorbed:Entity {id: $absorbed_id})-[r:BUYS_FROM]->(x:Entity)
        WHERE x.id <> $survivor_id
        MERGE (survivor:Entity {id: $survivor_id})
        MERGE (survivor)-[nr:BUYS_FROM]->(x)
        SET nr.volume = coalesce(nr.volume, 0) + coalesce(r.volume, 0),
            nr.count = coalesce(nr.count, 0) + coalesce(r.count, 0),
            nr.updated_at = datetime()
        DELETE r
        """
        cypher3 = """
        // Migrate incoming SELLS_TO edges
        MATCH (x:Entity)-[r:SELLS_TO]->(absorbed:Entity {id: $absorbed_id})
        WHERE x.id <> $survivor_id
        MERGE (survivor:Entity {id: $survivor_id})
        MERGE (x)-[nr:SELLS_TO]->(survivor)
        SET nr.volume = coalesce(nr.volume, 0) + coalesce(r.volume, 0),
            nr.count = coalesce(nr.count, 0) + coalesce(r.count, 0),
            nr.updated_at = datetime()
        DELETE r
        """
        cypher4 = """
        // Migrate outgoing SELLS_TO edges
        MATCH (absorbed:Entity {id: $absorbed_id})-[r:SELLS_TO]->(x:Entity)
        WHERE x.id <> $survivor_id
        MERGE (survivor:Entity {id: $survivor_id})
        MERGE (survivor)-[nr:SELLS_TO]->(x)
        SET nr.volume = coalesce(nr.volume, 0) + coalesce(r.volume, 0),
            nr.count = coalesce(nr.count, 0) + coalesce(r.count, 0),
            nr.updated_at = datetime()
        DELETE r
        """
        cypher5 = """
        // Mark absorbed as MERGED and create redirect
        MATCH (absorbed:Entity {id: $absorbed_id})
        MERGE (survivor:Entity {id: $survivor_id})
        SET absorbed.status = 'MERGED',
            absorbed.merged_into = $survivor_id
        MERGE (absorbed)-[:MERGED_INTO]->(survivor)
        """
        params = {"survivor_id": survivor_id, "absorbed_id": absorbed_id}
        try:
            with self._driver.session(database=self._cfg.database) as session:
                for q in [cypher, cypher2, cypher3, cypher4, cypher5]:
                    session.run(q, params)
        except Exception as e:
            logger.error(f"Neo4j merge_entities failed: {e}")

    def write_audit(self, audit_dict: dict) -> str:
        """Create an AuditEntry node for real-time reads (Paimon is compliance archive)."""
        if self._using_mock:
            self._mock_audit.append(audit_dict)
            return audit_dict.get("audit_id", "")
        if not self._available:
            return audit_dict.get("audit_id", "")
        cypher = """
        CREATE (a:AuditEntry {
            audit_id: $audit_id,
            event_id: $event_id,
            record_id: $record_id,
            perspective: $perspective,
            decision: $decision,
            trigger_type: $trigger_type,
            target_golden_id: $target_golden_id,
            absorbed_golden_id: $absorbed_golden_id,
            confidence: $confidence,
            dimension_scores: $dimension_scores,
            reasoning: $reasoning,
            key_factors: $key_factors,
            candidates_evaluated: $candidates_evaluated,
            llm_calls: $llm_calls,
            embedding_calls: $embedding_calls,
            total_duration_ms: $total_duration_ms,
            evaluation_chain: $evaluation_chain,
            golden_record_before: $golden_record_before,
            golden_record_after: $golden_record_after,
            created_at: datetime()
        })
        """
        params = {
            "audit_id": audit_dict.get("audit_id", ""),
            "event_id": audit_dict.get("event_id", ""),
            "record_id": audit_dict.get("record_id", ""),
            "perspective": audit_dict.get("perspective", "GLOBAL"),
            "decision": audit_dict.get("decision", ""),
            "trigger_type": audit_dict.get("trigger_type", "AI_AGENT"),
            "target_golden_id": audit_dict.get("target_golden_id"),
            "absorbed_golden_id": audit_dict.get("absorbed_golden_id"),
            "confidence": float(audit_dict.get("confidence", 0)),
            "dimension_scores": json.dumps(audit_dict.get("dimension_scores", {}), default=str),
            "reasoning": audit_dict.get("reasoning", ""),
            "key_factors": json.dumps(audit_dict.get("key_factors", []), default=str),
            "candidates_evaluated": int(audit_dict.get("candidates_evaluated", 0)),
            "llm_calls": int(audit_dict.get("llm_calls", 0)),
            "embedding_calls": int(audit_dict.get("embedding_calls", 0)),
            "total_duration_ms": int(audit_dict.get("total_duration_ms", 0)),
            "evaluation_chain": json.dumps(audit_dict.get("evaluation_chain", []), default=str),
            "golden_record_before": json.dumps(audit_dict.get("golden_record_before"), default=str),
            "golden_record_after": json.dumps(audit_dict.get("golden_record_after"), default=str),
        }
        try:
            with self._driver.session(database=self._cfg.database) as session:
                session.run(cypher, params)
            return params["audit_id"]
        except Exception as e:
            logger.error(f"Neo4j write_audit failed: {e}")
            return params["audit_id"]

    def delete_entity(self, entity_id: str):
        """Delete an entity node and all its relationships."""
        if not self._available:
            return
        cypher = "MATCH (e:Entity {id: $id}) DETACH DELETE e"
        try:
            with self._driver.session(database=self._cfg.database) as session:
                session.run(cypher, {"id": entity_id})
        except Exception as e:
            logger.error(f"Neo4j delete_entity failed: {e}")

    # ── Golden record read methods ───────────────────────────

    def get_golden_record(self, golden_record_id: str) -> Optional[dict]:
        """Point lookup by PK constraint — returns dict matching MySQL shape."""
        if self._using_mock:
            raw = self._mock_entities.get(golden_record_id)
            if not raw:
                return None
            d = dict(raw)
            d["golden_record_id"] = d.pop("id", golden_record_id)
            if d.get("persona") and isinstance(d["persona"], str):
                try:
                    d["persona"] = json.loads(d["persona"])
                except json.JSONDecodeError:
                    pass
            return d
        if not self._available:
            return None
        cypher = """
        MATCH (e:Entity {id: $id})
        RETURN e
        """
        try:
            with self._driver.session(database=self._cfg.database) as session:
                result = session.run(cypher, {"id": golden_record_id})
                record = result.single()
                if not record:
                    return None
                return self._entity_to_dict(record["e"])
        except Exception as e:
            logger.error(f"Neo4j get_golden_record failed: {e}")
            return None

    def get_all_golden_records(self, active_only: bool = True) -> list[dict]:
        """Read all golden records (for backfill/cold start)."""
        if self._using_mock:
            results = []
            for raw in self._mock_entities.values():
                if active_only and raw.get("status") not in ("ACTIVE", "PROVISIONAL"):
                    continue
                d = dict(raw)
                d["golden_record_id"] = d.pop("id", "")
                results.append(d)
            return results
        if not self._available:
            return []
        status_filter = "WHERE e.status IN ['ACTIVE', 'PROVISIONAL']" if active_only else ""
        cypher = f"MATCH (e:Entity) {status_filter} RETURN e"
        try:
            with self._driver.session(database=self._cfg.database) as session:
                result = session.run(cypher)
                return [self._entity_to_dict(record["e"]) for record in result]
        except Exception as e:
            logger.error(f"Neo4j get_all_golden_records failed: {e}")
            return []

    def find_by_bucket_key(self, bucket_key: str) -> list[str]:
        """Translate bucket key patterns to Cypher indexed queries.

        Returns list of golden_record_ids matching the bucket key.
        """
        if self._using_mock:
            return self._mock_find_by_bucket_key(bucket_key)
        if not self._available:
            return []

        parts = bucket_key.split(":", 1)
        if len(parts) != 2:
            return []
        prefix, value = parts

        try:
            with self._driver.session(database=self._cfg.database) as session:
                if prefix == "ein":
                    result = session.run(
                        "MATCH (e:Entity) WHERE e.ein = $v AND e.status <> 'MERGED' RETURN e.id AS id",
                        {"v": value})

                elif prefix == "name":
                    name_state = value.split("+", 1)
                    if len(name_state) == 2:
                        name_token, state = name_state
                        result = session.run(
                            "CALL db.index.fulltext.queryNodes('entity_name_ft', $q) YIELD node "
                            "WHERE node.state = $s AND node.status <> 'MERGED' "
                            "RETURN node.id AS id",
                            {"q": f"{name_token}*", "s": state})
                    else:
                        result = session.run(
                            "CALL db.index.fulltext.queryNodes('entity_name_ft', $q) YIELD node "
                            "WHERE node.status <> 'MERGED' RETURN node.id AS id",
                            {"q": f"{value}*"})

                elif prefix == "naics4":
                    naics_state = value.split("+", 1)
                    if len(naics_state) == 2:
                        naics_prefix, state = naics_state
                        result = session.run(
                            "MATCH (e:Entity) WHERE e.naics_code STARTS WITH $v "
                            "AND e.state = $s AND e.status <> 'MERGED' RETURN e.id AS id",
                            {"v": naics_prefix, "s": state})
                    else:
                        result = session.run(
                            "MATCH (e:Entity) WHERE e.naics_code STARTS WITH $v "
                            "AND e.status <> 'MERGED' RETURN e.id AS id",
                            {"v": value})

                elif prefix == "naics3":
                    naics_state = value.split("+", 1)
                    if len(naics_state) == 2:
                        naics_prefix, state = naics_state
                        result = session.run(
                            "MATCH (e:Entity) WHERE e.naics_subsector = $v "
                            "AND e.state = $s AND e.status <> 'MERGED' RETURN e.id AS id",
                            {"v": naics_prefix, "s": state})
                    else:
                        result = session.run(
                            "MATCH (e:Entity) WHERE e.naics_subsector = $v "
                            "AND e.status <> 'MERGED' RETURN e.id AS id",
                            {"v": value})

                elif prefix == "zip3":
                    result = session.run(
                        "MATCH (e:Entity) WHERE e.zip3 = $v AND e.status <> 'MERGED' RETURN e.id AS id",
                        {"v": value})

                elif prefix == "city":
                    city_state = value.split("+", 1)
                    if len(city_state) == 2:
                        city, state = city_state
                        result = session.run(
                            "MATCH (e:Entity) WHERE e.city = $c AND e.state = $s "
                            "AND e.status <> 'MERGED' RETURN e.id AS id",
                            {"c": city, "s": state})
                    else:
                        result = session.run(
                            "MATCH (e:Entity) WHERE e.city = $v AND e.status <> 'MERGED' RETURN e.id AS id",
                            {"v": value})

                elif prefix == "phone":
                    result = session.run(
                        "MATCH (e:Entity) WHERE e.phone_digits = $v AND e.status <> 'MERGED' RETURN e.id AS id",
                        {"v": value})

                elif prefix == "email_domain":
                    result = session.run(
                        "MATCH (e:Entity) WHERE e.email_domain = $v AND e.status <> 'MERGED' RETURN e.id AS id",
                        {"v": value})

                elif prefix == "commodity":
                    kw_state = value.split("+", 1)
                    if len(kw_state) == 2:
                        keyword, state = kw_state
                        result = session.run(
                            "MATCH (e:Entity) WHERE any(k IN e.commodity_keywords WHERE toLower(k) CONTAINS $v) "
                            "AND e.state = $s AND e.status <> 'MERGED' RETURN e.id AS id",
                            {"v": keyword.lower(), "s": state})
                    else:
                        result = session.run(
                            "MATCH (e:Entity) WHERE any(k IN e.commodity_keywords WHERE toLower(k) CONTAINS $v) "
                            "AND e.status <> 'MERGED' RETURN e.id AS id",
                            {"v": value.lower()})

                else:
                    logger.warning(f"Unknown bucket key prefix: {prefix}")
                    return []

                return [record["id"] for record in result]
        except Exception as e:
            logger.error(f"Neo4j find_by_bucket_key failed for {bucket_key}: {e}")
            return []

    def search_by_name(
        self,
        query: str,
        state_filter: str = None,
        city_filter: str = None,
        naics_filter: str = None,
        min_confidence: float = None,
        limit: int = 10,
    ) -> list[dict]:
        """Three-tier name search: exact, CONTAINS, fulltext."""
        if self._using_mock:
            return self._mock_search_by_name(
                query, state_filter, city_filter, naics_filter, min_confidence, limit)
        if not self._available:
            return []

        filters = ["e.status <> 'MERGED'"]
        params: dict = {"limit": limit}
        if state_filter:
            filters.append("e.state = $state")
            params["state"] = state_filter.upper()
        if city_filter:
            filters.append("toUpper(e.city) = $city")
            params["city"] = city_filter.upper()
        if naics_filter:
            filters.append("e.naics_code STARTS WITH $naics")
            params["naics"] = naics_filter
        if min_confidence is not None:
            filters.append("e.confidence >= $min_conf")
            params["min_conf"] = min_confidence
        where = " AND ".join(filters)

        query_upper = query.strip().upper()
        results = []
        seen_ids = set()

        try:
            with self._driver.session(database=self._cfg.database) as session:
                # Tier 1: exact match
                params["q_exact"] = query_upper
                cypher1 = f"""
                MATCH (e:Entity) WHERE toUpper(e.canonical_name) = $q_exact AND {where}
                RETURN e, 1.0 AS match_rank LIMIT $limit
                """
                for record in session.run(cypher1, params):
                    d = self._entity_to_summary(record["e"])
                    d["match_rank"] = record["match_rank"]
                    if d["golden_record_id"] not in seen_ids:
                        seen_ids.add(d["golden_record_id"])
                        results.append(d)

                # Tier 2: CONTAINS partial match
                if len(results) < limit:
                    params["q_contains"] = query_upper
                    cypher2 = f"""
                    MATCH (e:Entity) WHERE toUpper(e.canonical_name) CONTAINS $q_contains AND {where}
                    RETURN e, 0.8 AS match_rank ORDER BY e.confidence DESC LIMIT $limit
                    """
                    for record in session.run(cypher2, params):
                        d = self._entity_to_summary(record["e"])
                        d["match_rank"] = record["match_rank"]
                        if d["golden_record_id"] not in seen_ids:
                            seen_ids.add(d["golden_record_id"])
                            results.append(d)

                # Tier 3: fulltext index
                if len(results) < limit:
                    words = [w for w in query.strip().split() if len(w) > 1]
                    ft_query = " ".join(f"{w}*" for w in words)
                    if ft_query:
                        params["ft_q"] = ft_query
                        cypher3 = f"""
                        CALL db.index.fulltext.queryNodes('entity_name_ft', $ft_q) YIELD node AS e, score
                        WHERE {where}
                        RETURN e, 0.6 AS match_rank ORDER BY score DESC LIMIT $limit
                        """
                        for record in session.run(cypher3, params):
                            d = self._entity_to_summary(record["e"])
                            d["match_rank"] = record["match_rank"]
                            if d["golden_record_id"] not in seen_ids:
                                seen_ids.add(d["golden_record_id"])
                                results.append(d)

            return results[:limit]
        except Exception as e:
            logger.error(f"Neo4j search_by_name failed: {e}")
            return []

    def aggregate_golden_records(
        self,
        group_by: str,
        state_filter: str = None,
        naics_filter: str = None,
        min_confidence: float = None,
    ) -> list[dict]:
        """Cypher GROUP BY aggregation on Entity nodes."""
        if self._using_mock:
            return self._mock_aggregate(group_by, state_filter, naics_filter, min_confidence)
        if not self._available:
            return []

        allowed_columns = {
            "state": "e.state",
            "naics_sector": "e.naics_sector",
            "naics_subsector": "e.naics_subsector",
            "city": "e.city",
            "volume_bracket": "e.volume_bracket",
            "entity_type": "e.entity_type",
            "industry": "e.naics_sector",
        }

        if group_by == "confidence_range":
            return self._aggregate_confidence_ranges(state_filter, naics_filter, min_confidence)

        col = allowed_columns.get(group_by)
        if col is None:
            return [{"error": f"Invalid group_by: {group_by}. Allowed: {list(allowed_columns.keys())}"}]

        conditions = ["e.status <> 'MERGED'"]
        params: dict = {}
        if state_filter:
            conditions.append("e.state = $state")
            params["state"] = state_filter
        if naics_filter:
            conditions.append("e.naics_code STARTS WITH $naics")
            params["naics"] = naics_filter
        if min_confidence is not None:
            conditions.append("e.confidence >= $min_conf")
            params["min_conf"] = min_confidence

        where = " AND ".join(conditions)
        cypher = f"""
        MATCH (e:Entity) WHERE {where}
        RETURN {col} AS group_value, count(e) AS count
        ORDER BY count DESC
        """
        try:
            with self._driver.session(database=self._cfg.database) as session:
                result = session.run(cypher, params)
                return [{"group_value": r["group_value"], "count": r["count"]} for r in result]
        except Exception as e:
            logger.error(f"Neo4j aggregate_golden_records failed: {e}")
            return []

    def _aggregate_confidence_ranges(
        self, state_filter: str = None, naics_filter: str = None, min_confidence: float = None,
    ) -> list[dict]:
        """Aggregate by confidence ranges: <0.60, 0.60-0.85, >0.85."""
        conditions = ["e.status <> 'MERGED'"]
        params: dict = {}
        if state_filter:
            conditions.append("e.state = $state")
            params["state"] = state_filter
        if naics_filter:
            conditions.append("e.naics_code STARTS WITH $naics")
            params["naics"] = naics_filter
        if min_confidence is not None:
            conditions.append("e.confidence >= $min_conf")
            params["min_conf"] = min_confidence
        where = " AND ".join(conditions)
        cypher = f"""
        MATCH (e:Entity) WHERE {where}
        RETURN
            CASE
                WHEN e.confidence >= 0.85 THEN 'high (>=0.85)'
                WHEN e.confidence >= 0.60 THEN 'medium (0.60-0.85)'
                ELSE 'low (<0.60)'
            END AS group_value,
            count(e) AS count
        ORDER BY count DESC
        """
        try:
            with self._driver.session(database=self._cfg.database) as session:
                result = session.run(cypher, params)
                return [{"group_value": r["group_value"], "count": r["count"]} for r in result]
        except Exception as e:
            logger.error(f"Neo4j _aggregate_confidence_ranges failed: {e}")
            return []

    def get_audit_trail(self, entity_id: str, limit: int = 50) -> list[dict]:
        """Read AuditEntry nodes for an entity."""
        if self._using_mock:
            matches = [a for a in self._mock_audit
                       if a.get("target_golden_id") == entity_id
                       or a.get("record_id") == entity_id
                       or a.get("absorbed_golden_id") == entity_id]
            matches.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return matches[:limit]
        if not self._available:
            return []
        cypher = """
        MATCH (a:AuditEntry)
        WHERE a.target_golden_id = $id OR a.record_id = $id OR a.absorbed_golden_id = $id
        RETURN a ORDER BY a.created_at DESC LIMIT $limit
        """
        try:
            with self._driver.session(database=self._cfg.database) as session:
                result = session.run(cypher, {"id": entity_id, "limit": limit})
                rows = []
                for record in result:
                    node = record["a"]
                    d = dict(node)
                    # Deserialize JSON string fields
                    for col in ["dimension_scores", "key_factors", "evaluation_chain",
                                "golden_record_before", "golden_record_after"]:
                        if d.get(col) and isinstance(d[col], str):
                            try:
                                d[col] = json.loads(d[col])
                            except json.JSONDecodeError:
                                pass
                    # Convert Neo4j DateTime to ISO string
                    if d.get("created_at") and hasattr(d["created_at"], "iso_format"):
                        d["created_at"] = d["created_at"].iso_format()
                    rows.append(d)
                return rows
        except Exception as e:
            logger.error(f"Neo4j get_audit_trail failed: {e}")
            return []

    def get_relationships(
        self,
        company_id: str,
        connection_type: str = "all",
        sort_by: str = "volume",
        limit: int = 50,
    ) -> list[dict]:
        """Get relationships for a company, filtered by connection type."""
        if not self._available:
            return []

        order = {"volume": "volume DESC", "count": "count DESC", "name": "name ASC"}.get(sort_by, "volume DESC")

        if connection_type == "vendor":
            cypher = f"""
            MATCH (c:Entity {{id: $id}})-[r:BUYS_FROM]->(v:Entity)
            WHERE v.status IN ['ACTIVE', 'PROVISIONAL']
            RETURN r.edge_id AS edge_id, c.id AS source_entity_id, v.id AS target_entity_id,
                   r.volume AS transaction_volume, r.count AS transaction_count,
                   v.canonical_name AS canonical_name, v.state AS state, v.city AS city,
                   v.naics_code AS naics_code, v.confidence AS confidence,
                   v.entity_type AS entity_type, v.source_count AS source_count,
                   'vendor' AS connection_type, r.volume AS volume, v.canonical_name AS name
            ORDER BY {order} LIMIT $limit
            """
            params = {"id": company_id, "limit": limit}
        elif connection_type == "customer":
            cypher = f"""
            MATCH (cust:Entity)-[r:BUYS_FROM]->(c:Entity {{id: $id}})
            WHERE cust.status IN ['ACTIVE', 'PROVISIONAL']
            RETURN r.edge_id AS edge_id, cust.id AS source_entity_id, c.id AS target_entity_id,
                   r.volume AS transaction_volume, r.count AS transaction_count,
                   cust.canonical_name AS canonical_name, cust.state AS state, cust.city AS city,
                   cust.naics_code AS naics_code, cust.confidence AS confidence,
                   cust.entity_type AS entity_type, cust.source_count AS source_count,
                   'customer' AS connection_type, r.volume AS volume, cust.canonical_name AS name
            ORDER BY {order} LIMIT $limit
            """
            params = {"id": company_id, "limit": limit}
        else:
            cypher = f"""
            MATCH (c:Entity {{id: $id}})-[r]->(other:Entity)
            WHERE other.status IN ['ACTIVE', 'PROVISIONAL']
            RETURN r.edge_id AS edge_id, c.id AS source_entity_id, other.id AS target_entity_id,
                   r.volume AS transaction_volume, r.count AS transaction_count,
                   other.canonical_name AS canonical_name, other.state AS state, other.city AS city,
                   other.naics_code AS naics_code, other.confidence AS confidence,
                   other.entity_type AS entity_type, other.source_count AS source_count,
                   CASE type(r) WHEN 'BUYS_FROM' THEN 'vendor' ELSE 'customer' END AS connection_type,
                   r.volume AS volume, other.canonical_name AS name
            UNION ALL
            MATCH (other:Entity)-[r]->(c:Entity {{id: $id}})
            WHERE other.status IN ['ACTIVE', 'PROVISIONAL']
            RETURN r.edge_id AS edge_id, other.id AS source_entity_id, c.id AS target_entity_id,
                   r.volume AS transaction_volume, r.count AS transaction_count,
                   other.canonical_name AS canonical_name, other.state AS state, other.city AS city,
                   other.naics_code AS naics_code, other.confidence AS confidence,
                   other.entity_type AS entity_type, other.source_count AS source_count,
                   CASE type(r) WHEN 'BUYS_FROM' THEN 'customer' ELSE 'vendor' END AS connection_type,
                   r.volume AS volume, other.canonical_name AS name
            ORDER BY {order} LIMIT $limit
            """
            params = {"id": company_id, "limit": limit}

        try:
            with self._driver.session(database=self._cfg.database) as session:
                result = session.run(cypher, params)
                return [dict(r) for r in result]
        except Exception as e:
            logger.error(f"Neo4j get_relationships failed: {e}")
            return []

    @property
    def record_count(self) -> int:
        """Count of non-MERGED Entity nodes."""
        if self._using_mock:
            return sum(1 for e in self._mock_entities.values() if e.get("status") != "MERGED")
        if not self._available:
            return 0
        try:
            with self._driver.session(database=self._cfg.database) as session:
                result = session.run("MATCH (e:Entity) WHERE e.status <> 'MERGED' RETURN count(e) AS cnt")
                return result.single()["cnt"]
        except Exception:
            return 0

    @staticmethod
    def generate_id(prefix: str = "G") -> str:
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    # ── In-memory mock helpers (for tests) ───────────────────

    def _mock_find_by_bucket_key(self, bucket_key: str) -> list[str]:
        """In-memory bucket key search matching Cypher behavior."""
        parts = bucket_key.split(":", 1)
        if len(parts) != 2:
            return []
        prefix, value = parts

        results = []
        for eid, e in self._mock_entities.items():
            if e.get("status") == "MERGED":
                continue

            if prefix == "ein":
                if e.get("ein") == value:
                    results.append(eid)
            elif prefix == "name":
                name_state = value.split("+", 1)
                name_token = name_state[0]
                state = name_state[1] if len(name_state) == 2 else None
                cname = (e.get("canonical_name") or "").upper()
                if name_token.upper() in cname:
                    if state is None or e.get("state") == state:
                        results.append(eid)
            elif prefix == "naics4":
                naics_state = value.split("+", 1)
                naics_prefix = naics_state[0]
                state = naics_state[1] if len(naics_state) == 2 else None
                if (e.get("naics_code") or "").startswith(naics_prefix):
                    if state is None or e.get("state") == state:
                        results.append(eid)
            elif prefix == "naics3":
                naics_state = value.split("+", 1)
                naics_sub = naics_state[0]
                state = naics_state[1] if len(naics_state) == 2 else None
                if e.get("naics_subsector") == naics_sub:
                    if state is None or e.get("state") == state:
                        results.append(eid)
            elif prefix == "zip3":
                if e.get("zip3") == value:
                    results.append(eid)
            elif prefix == "city":
                city_state = value.split("+", 1)
                if len(city_state) == 2:
                    if e.get("city") == city_state[0] and e.get("state") == city_state[1]:
                        results.append(eid)
                elif e.get("city") == value:
                    results.append(eid)
            elif prefix == "phone":
                if e.get("phone_digits") == value:
                    results.append(eid)
            elif prefix == "email_domain":
                if e.get("email_domain") == value:
                    results.append(eid)
            elif prefix == "commodity":
                kw_state = value.split("+", 1)
                keyword = kw_state[0].lower()
                state = kw_state[1] if len(kw_state) == 2 else None
                kws = e.get("commodity_keywords") or []
                if any(keyword in k.lower() for k in kws):
                    if state is None or e.get("state") == state:
                        results.append(eid)

        return results

    def _mock_search_by_name(
        self, query, state_filter, city_filter, naics_filter, min_confidence, limit,
    ) -> list[dict]:
        """In-memory name search for tests."""
        q_upper = query.strip().upper()
        results = []
        for eid, e in self._mock_entities.items():
            if e.get("status") == "MERGED":
                continue
            cname = (e.get("canonical_name") or "").upper()
            if q_upper not in cname:
                continue
            if state_filter and (e.get("state") or "").upper() != state_filter.upper():
                continue
            if city_filter and (e.get("city") or "").upper() != city_filter.upper():
                continue
            if naics_filter and not (e.get("naics_code") or "").startswith(naics_filter):
                continue
            if min_confidence is not None and float(e.get("confidence", 0)) < min_confidence:
                continue
            results.append({
                "golden_record_id": eid,
                "canonical_name": e.get("canonical_name", ""),
                "state": e.get("state", ""),
                "city": e.get("city", ""),
                "naics_code": e.get("naics_code", ""),
                "naics_sector": e.get("naics_sector", ""),
                "confidence": float(e.get("confidence", 0)),
                "entity_type": e.get("entity_type", ""),
                "source_count": int(e.get("source_count", 1)),
                "match_rank": 0.9,
            })
        return results[:limit]

    def _mock_aggregate(self, group_by, state_filter, naics_filter, min_confidence) -> list[dict]:
        """In-memory aggregation for tests."""
        allowed_columns = {
            "state": "state", "naics_sector": "naics_sector",
            "naics_subsector": "naics_subsector", "city": "city",
            "volume_bracket": "volume_bracket", "entity_type": "entity_type",
            "industry": "naics_sector",
        }

        if group_by == "confidence_range":
            return self._mock_aggregate_confidence_range(state_filter, naics_filter, min_confidence)

        col = allowed_columns.get(group_by)
        if col is None:
            return [{"error": f"Invalid group_by: {group_by}. Allowed: {list(allowed_columns.keys())}"}]

        groups: dict[str, int] = {}
        for e in self._mock_entities.values():
            if e.get("status") == "MERGED":
                continue
            if state_filter and e.get("state") != state_filter:
                continue
            if naics_filter and not (e.get("naics_code") or "").startswith(naics_filter):
                continue
            if min_confidence is not None and float(e.get("confidence", 0)) < min_confidence:
                continue
            val = e.get(col) or "Unknown"
            groups[val] = groups.get(val, 0) + 1

        return [{"group_value": k, "count": v} for k, v in sorted(groups.items(), key=lambda x: -x[1])]

    def _mock_aggregate_confidence_range(self, state_filter, naics_filter, min_confidence) -> list[dict]:
        """In-memory confidence range aggregation for tests."""
        groups: dict[str, int] = {}
        for e in self._mock_entities.values():
            if e.get("status") == "MERGED":
                continue
            if state_filter and e.get("state") != state_filter:
                continue
            if naics_filter and not (e.get("naics_code") or "").startswith(naics_filter):
                continue
            conf = float(e.get("confidence", 0))
            if min_confidence is not None and conf < min_confidence:
                continue
            if conf >= 0.85:
                label = "high (>=0.85)"
            elif conf >= 0.60:
                label = "medium (0.60-0.85)"
            else:
                label = "low (<0.60)"
            groups[label] = groups.get(label, 0) + 1
        return [{"group_value": k, "count": v} for k, v in sorted(groups.items(), key=lambda x: -x[1])]

    # ── Entity dict conversion helpers ───────────────────────

    def _entity_to_dict(self, node) -> dict:
        """Convert a Neo4j Entity node to a dict matching the MySQL golden_records shape."""
        d = dict(node)
        # Remap 'id' → 'golden_record_id'
        d["golden_record_id"] = d.pop("id", "")
        # Deserialize JSON string fields
        for col in ["persona"]:
            if d.get(col) and isinstance(d[col], str):
                try:
                    d[col] = json.loads(d[col])
                except json.JSONDecodeError:
                    pass
        # Convert Neo4j DateTime to ISO string
        for col in ["created_at", "updated_at"]:
            val = d.get(col)
            if val and hasattr(val, "iso_format"):
                d[col] = val.iso_format()
        return d

    def _entity_to_summary(self, node) -> dict:
        """Convert a Neo4j Entity node to a summary dict for search results."""
        d = dict(node)
        return {
            "golden_record_id": d.get("id", ""),
            "canonical_name": d.get("canonical_name", ""),
            "state": d.get("state", ""),
            "city": d.get("city", ""),
            "naics_code": d.get("naics_code", ""),
            "naics_sector": d.get("naics_sector", ""),
            "confidence": d.get("confidence", 0),
            "entity_type": d.get("entity_type", ""),
            "source_count": d.get("source_count", 1),
        }

    # ── Graph traversal read methods ─────────────────────────

    def traverse_supply_chain(
        self,
        start_id: str,
        hops: list[str],
        max_per_hop: int = 5,
        min_volume: float = 0,
    ) -> list[dict]:
        """Directed multi-hop supply chain traversal.

        Args:
            start_id: Starting entity ID.
            hops: List of hop directions, e.g. ["vendor", "client", "vendor"].
            max_per_hop: Max entities to follow per hop (sorted by volume).
            min_volume: Minimum transaction volume to include.

        Returns:
            List of path dicts with chain, edges, total_volume.
        """
        if not self._available:
            return []

        # Build Cypher path pattern from hop list
        node_vars = ["n0"]
        rel_vars = []
        match_parts = ["(n0:Entity {id: $start_id})"]
        where_parts = []

        for i, hop in enumerate(hops):
            pattern = _HOP_PATTERNS.get(hop)
            if not pattern:
                logger.warning(f"Unknown hop direction: {hop}")
                return []
            node_var = f"n{i + 1}"
            rel_var = f"r{i}"
            node_vars.append(node_var)
            rel_vars.append(rel_var)

            # Extract rel type from pattern (e.g., "BUYS_FROM" from "-[:BUYS_FROM]->")
            rel_type = pattern.split("[:")[-1].split("]")[0]
            match_parts.append(f"-[{rel_var}:{rel_type}]->({node_var}:Entity)")
            where_parts.append(f"{node_var}.status = 'ACTIVE'")

        if min_volume > 0:
            for rv in rel_vars:
                where_parts.append(f"{rv}.volume >= $min_volume")

        match_clause = "MATCH path = " + "".join(match_parts)
        where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""

        # Build volume sum
        vol_sum = " + ".join(f"coalesce({rv}.volume, 0)" for rv in rel_vars)
        if not vol_sum:
            vol_sum = "0"

        cypher = f"""
        {match_clause}
        {where_clause}
        WITH path, {vol_sum} AS total_volume,
             {', '.join(node_vars)}, {', '.join(rel_vars) if rel_vars else '0 AS _dummy'}
        ORDER BY total_volume DESC
        LIMIT $max_paths
        RETURN [n IN nodes(path) | {{id: n.id, name: n.canonical_name, type: n.entity_type, status: n.status}}] AS chain,
               [r IN relationships(path) | {{type: type(r), volume: r.volume, count: r.count}}] AS edges,
               total_volume
        """

        params = {
            "start_id": start_id,
            "min_volume": min_volume,
            "max_paths": max_per_hop * 10,
        }

        try:
            with self._driver.session(database=self._cfg.database) as session:
                result = session.run(cypher, params)
                paths = []
                for record in result:
                    paths.append({
                        "chain": record["chain"],
                        "edges": record["edges"],
                        "total_volume": record["total_volume"],
                    })
                return paths
        except Exception as e:
            logger.error(f"Neo4j traverse_supply_chain failed: {e}")
            return []

    def get_entity_neighbors(
        self, entity_id: str, direction: str = "both", rel_type: str = None,
    ) -> list[dict]:
        """Get direct neighbors of an entity with direction support."""
        if self._using_mock:
            results = []
            for rel in self._mock_relationships.values():
                r_type = rel.get("rel_type", "")
                if rel_type and r_type != rel_type:
                    continue
                src, tgt = rel["source_entity_id"], rel["target_entity_id"]
                if direction == "outgoing" and src == entity_id:
                    target = self._mock_entities.get(tgt, {})
                    results.append({
                        "id": tgt, "name": target.get("canonical_name", ""),
                        "type": target.get("entity_type", ""), "rel_type": r_type,
                        "volume": rel.get("volume"), "count": rel.get("count"),
                        "is_outgoing": True,
                    })
                elif direction == "incoming" and tgt == entity_id:
                    source = self._mock_entities.get(src, {})
                    results.append({
                        "id": src, "name": source.get("canonical_name", ""),
                        "type": source.get("entity_type", ""), "rel_type": r_type,
                        "volume": rel.get("volume"), "count": rel.get("count"),
                        "is_outgoing": False,
                    })
                elif direction == "both" and (src == entity_id or tgt == entity_id):
                    other_id = tgt if src == entity_id else src
                    other = self._mock_entities.get(other_id, {})
                    results.append({
                        "id": other_id, "name": other.get("canonical_name", ""),
                        "type": other.get("entity_type", ""), "rel_type": r_type,
                        "volume": rel.get("volume"), "count": rel.get("count"),
                        "is_outgoing": src == entity_id,
                    })
            return results
        if not self._available:
            return []

        if direction == "outgoing":
            pattern = "(e:Entity {id: $id})-[r]->(n:Entity)"
        elif direction == "incoming":
            pattern = "(n:Entity)-[r]->(e:Entity {id: $id})"
        else:
            pattern = "(e:Entity {id: $id})-[r]-(n:Entity)"

        type_filter = f" AND type(r) = '{rel_type}'" if rel_type else ""
        cypher = f"""
        MATCH {pattern}
        WHERE n.status <> 'MERGED'{type_filter}
        RETURN n.id AS id, n.canonical_name AS name, n.entity_type AS type,
               type(r) AS rel_type, r.volume AS volume, r.count AS count,
               startNode(r).id = e.id AS is_outgoing
        ORDER BY r.volume DESC
        """
        try:
            with self._driver.session(database=self._cfg.database) as session:
                result = session.run(cypher, {"id": entity_id})
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Neo4j get_entity_neighbors failed: {e}")
            return []

    def find_shortest_path(self, start_id: str, end_id: str) -> Optional[dict]:
        """Find shortest path between two entities (any direction)."""
        if not self._available:
            return None
        cypher = """
        MATCH path = shortestPath(
            (s:Entity {id: $start_id})-[*..6]-(t:Entity {id: $end_id})
        )
        WHERE ALL(n IN nodes(path) WHERE n.status <> 'MERGED')
        RETURN [n IN nodes(path) | {id: n.id, name: n.canonical_name, type: n.entity_type}] AS chain,
               [r IN relationships(path) | {type: type(r), volume: r.volume}] AS edges,
               length(path) AS hops
        """
        try:
            with self._driver.session(database=self._cfg.database) as session:
                result = session.run(cypher, {"start_id": start_id, "end_id": end_id})
                record = result.single()
                if record:
                    return {
                        "chain": record["chain"],
                        "edges": record["edges"],
                        "hops": record["hops"],
                    }
                return None
        except Exception as e:
            logger.error(f"Neo4j find_shortest_path failed: {e}")
            return None

    def detect_cycles(self, entity_id: str, max_depth: int = 4) -> list[dict]:
        """Detect circular paths starting and ending at the given entity."""
        if not self._available:
            return []
        cypher = """
        MATCH path = (start:Entity {id: $id})-[*2..%d]->(start)
        WHERE ALL(n IN nodes(path) WHERE n.status <> 'MERGED')
        WITH path, length(path) AS cycle_length
        ORDER BY cycle_length
        LIMIT 10
        RETURN [n IN nodes(path) | {id: n.id, name: n.canonical_name}] AS chain,
               [r IN relationships(path) | {type: type(r), volume: r.volume}] AS edges,
               cycle_length
        """ % max_depth
        try:
            with self._driver.session(database=self._cfg.database) as session:
                result = session.run(cypher, {"id": entity_id})
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Neo4j detect_cycles failed: {e}")
            return []

    def find_common_neighbors(
        self, id_a: str, id_b: str, limit: int = 20,
    ) -> list[dict]:
        """Find entities that are direct transaction partners of both id_a and id_b."""
        if not self._available:
            return []
        cypher = """
        MATCH (a:Entity {id: $id_a})-[r1]-(shared:Entity)-[r2]-(b:Entity {id: $id_b})
        WHERE shared.status <> 'MERGED'
          AND shared.id <> $id_a AND shared.id <> $id_b
        RETURN DISTINCT shared.id AS id, shared.canonical_name AS name,
               shared.naics_code AS naics_code,
               type(r1) AS rel_to_a, r1.volume AS vol_a,
               type(r2) AS rel_to_b, r2.volume AS vol_b
        ORDER BY (coalesce(r1.volume, 0) + coalesce(r2.volume, 0)) DESC
        LIMIT $limit
        """
        try:
            with self._driver.session(database=self._cfg.database) as session:
                result = session.run(cypher, {
                    "id_a": id_a, "id_b": id_b, "limit": limit,
                })
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Neo4j find_common_neighbors failed: {e}")
            return []

    def find_cluster(
        self, entity_id: str, max_size: int = 20,
    ) -> Optional[dict]:
        """Discover the business cluster (ego-graph) around an entity within 3 hops."""
        if not self._available:
            return None
        # Step 1: find cluster member nodes via BFS (undirected, 3 hops)
        cypher_nodes = """
        MATCH (seed:Entity {id: $id})-[*1..3]-(n:Entity)
        WHERE n.status <> 'MERGED' AND n.id <> $id
        WITH DISTINCT n
        LIMIT $max_size
        RETURN collect(n.id) AS member_ids,
               collect({id: n.id, name: n.canonical_name, naics_code: n.naics_code}) AS members
        """
        try:
            with self._driver.session(database=self._cfg.database) as session:
                res = session.run(cypher_nodes, {"id": entity_id, "max_size": max_size})
                record = res.single()
                if not record:
                    return {"nodes": [], "edges": [], "density": 0.0, "center": entity_id}

                member_ids = record["member_ids"]
                members = record["members"]
                all_ids = member_ids + [entity_id]

                # Step 2: find internal edges among cluster members
                cypher_edges = """
                MATCH (a:Entity)-[r]->(b:Entity)
                WHERE a.id IN $ids AND b.id IN $ids
                RETURN a.id AS source, b.id AS target, type(r) AS rel_type,
                       r.volume AS volume
                """
                edge_result = session.run(cypher_edges, {"ids": all_ids})
                edges = [dict(r) for r in edge_result]

                # Compute density: edges / (n * (n-1))
                n = len(all_ids)
                max_edges = n * (n - 1) if n > 1 else 1
                density = round(len(edges) / max_edges, 3)

                return {
                    "nodes": members,
                    "edges": edges,
                    "density": density,
                    "center": entity_id,
                }
        except Exception as e:
            logger.error(f"Neo4j find_cluster failed: {e}")
            return None

    def assess_impact(
        self, entity_id: str, max_depth: int = 3,
    ) -> Optional[dict]:
        """Analyze downstream impact: who depends on this entity (buys from it)."""
        if not self._available:
            return None
        cypher = """
        MATCH path = (dependent:Entity)-[:BUYS_FROM*1..%d]->(target:Entity {id: $id})
        WHERE ALL(n IN nodes(path) WHERE n.status <> 'MERGED')
          AND dependent.id <> $id
        WITH dependent, length(path) AS depth,
             relationships(path)[0].volume AS first_edge_volume
        RETURN DISTINCT dependent.id AS id, dependent.canonical_name AS name,
               depth, coalesce(first_edge_volume, 0) AS volume_at_risk
        ORDER BY depth, volume_at_risk DESC
        """ % max_depth
        try:
            with self._driver.session(database=self._cfg.database) as session:
                result = session.run(cypher, {"id": entity_id})
                affected = [dict(r) for r in result]

                total_volume = sum(a.get("volume_at_risk", 0) for a in affected)
                depth_dist = {}
                for a in affected:
                    d = a.get("depth", 1)
                    depth_dist[d] = depth_dist.get(d, 0) + 1

                return {
                    "affected": affected,
                    "total_volume_at_risk": total_volume,
                    "depth_distribution": depth_dist,
                }
        except Exception as e:
            logger.error(f"Neo4j assess_impact failed: {e}")
            return None

    # ── T-Box: NAICS taxonomy (replaces GraphDB SPARQL) ──────

    @staticmethod
    def query_naics_hierarchy(code: str) -> list[str]:
        """Walk NAICS hierarchy upward via code structure.

        Pure Python — no DB call needed. NAICS encodes hierarchy in digits:
          238220 → [238220, 23822, 2382, 238, 23]
        """
        if not code:
            return []
        ancestors = []
        for length in range(len(code), 1, -1):
            ancestors.append(code[:length])
        return ancestors

    @staticmethod
    def query_lowest_common_ancestor(code_a: str, code_b: str) -> Optional[str]:
        """Find LCA of two NAICS codes via shared prefix.

        Pure Python — NAICS hierarchy is encoded in the code digits.
        """
        if not code_a or not code_b:
            return None
        shared = 0
        for a, b in zip(code_a, code_b):
            if a == b:
                shared += 1
            else:
                break
        if shared >= 2:
            return code_a[:shared]
        return None

    def query_cross_taxonomy_links(self, code_a: str, code_b: str) -> list[dict]:
        """Find shared commodity links between NAICS codes via Neo4j.

        Falls back to static known-links if Neo4j is unavailable.
        """
        if not code_a or not code_b:
            return []

        # Try Neo4j first
        if self._available:
            cypher = """
            MATCH (a:NAICSCode {code: $code_a})-[:COMMODITY_LINK]->(c)<-[:COMMODITY_LINK]-(b:NAICSCode {code: $code_b})
            RETURN c.code AS code, c.label AS label
            """
            try:
                with self._driver.session(database=self._cfg.database) as session:
                    result = session.run(cypher, {"code_a": code_a, "code_b": code_b})
                    links = [{"code": r["code"], "label": r["label"]} for r in result]
                    if links:
                        return links
            except Exception as e:
                logger.debug(f"Neo4j cross-taxonomy query failed: {e}")

        # Fallback: check static known cross-links
        return _static_cross_taxonomy_links(code_a, code_b)

    def query_shared_neighbors(self, entity_id: str) -> list[dict]:
        """Get entity's transaction partners (replaces GraphDB SPARQL query)."""
        neighbors = self.get_entity_neighbors(entity_id, direction="both")
        return [
            {
                "neighbor": n.get("id", ""),
                "name": n.get("name", ""),
                "naics": "",  # Would need enrichment from MySQL
            }
            for n in neighbors
        ]

    def _seed_cross_taxonomy_links(self):
        """Seed common cross-taxonomy commodity links into Neo4j.

        These represent NAICS codes from different sectors that share
        commodity supply chains (e.g., plumbing wholesaler ↔ plumbing contractor).
        """
        if not self._available:
            return
        for (code_a, code_b, commodity_code, commodity_label) in _CROSS_TAXONOMY_SEEDS:
            cypher = """
            MERGE (a:NAICSCode {code: $code_a})
            MERGE (b:NAICSCode {code: $code_b})
            MERGE (c:Commodity {code: $commodity_code})
            SET c.label = $commodity_label
            MERGE (a)-[:COMMODITY_LINK]->(c)
            MERGE (b)-[:COMMODITY_LINK]->(c)
            """
            try:
                with self._driver.session(database=self._cfg.database) as session:
                    session.run(cypher, {
                        "code_a": code_a, "code_b": code_b,
                        "commodity_code": commodity_code,
                        "commodity_label": commodity_label,
                    })
            except Exception as e:
                logger.debug(f"Seed cross-taxonomy failed: {e}")
        logger.info(f"Seeded {len(_CROSS_TAXONOMY_SEEDS)} cross-taxonomy commodity links")


# ── Static cross-taxonomy data ────────────────────────────

# (naics_a, naics_b, commodity_code, commodity_label)
# Represents known supply chain links across NAICS sectors
_CROSS_TAXONOMY_SEEDS = [
    # Plumbing: wholesaler ↔ contractor
    ("423720", "238220", "PLB-001", "Plumbing supplies & fixtures"),
    # Electrical: wholesaler ↔ contractor
    ("423610", "238210", "ELC-001", "Electrical wiring & equipment"),
    # HVAC: wholesaler ↔ contractor
    ("423730", "238220", "HVC-001", "HVAC equipment & parts"),
    # Lumber: wholesaler ↔ framing contractor
    ("423310", "238130", "LBR-001", "Lumber & wood products"),
    # Lumber: wholesaler ↔ general construction
    ("423310", "236220", "LBR-002", "Construction lumber & materials"),
    # Concrete: manufacturer ↔ foundation contractor
    ("327320", "238110", "CON-001", "Ready-mix concrete"),
    # Paint: wholesaler ↔ painting contractor
    ("423950", "238320", "PNT-001", "Paint & coating supplies"),
    # Roofing: wholesaler ↔ roofing contractor
    ("423330", "238160", "ROF-001", "Roofing materials"),
    # Hardware: wholesaler ↔ general contractor
    ("423710", "236220", "HDW-001", "Hardware & tools"),
    # Steel: manufacturer ↔ structural contractor
    ("331110", "238120", "STL-001", "Structural steel"),
    # Glass: manufacturer ↔ glazing contractor
    ("327211", "238150", "GLS-001", "Flat glass & glazing"),
    # Insulation: manufacturer ↔ insulation contractor
    ("327993", "238310", "INS-001", "Insulation materials"),
    # Landscaping supply ↔ landscaping services
    ("444220", "561730", "LND-001", "Landscaping supplies"),
    # Office supplies ↔ office admin services
    ("424120", "561110", "OFS-001", "Office supplies & stationery"),
    # Janitorial supply ↔ janitorial services
    ("423850", "561720", "JAN-001", "Janitorial supplies"),
]

# Precompute static lookup for fallback (no Neo4j)
_STATIC_CROSS_LINKS: dict[tuple[str, str], list[dict]] = {}
for _a, _b, _code, _label in _CROSS_TAXONOMY_SEEDS:
    _STATIC_CROSS_LINKS.setdefault((_a, _b), []).append({"code": _code, "label": _label})
    _STATIC_CROSS_LINKS.setdefault((_b, _a), []).append({"code": _code, "label": _label})


def _static_cross_taxonomy_links(code_a: str, code_b: str) -> list[dict]:
    """Check static known cross-taxonomy links between two NAICS codes."""
    # Exact match
    links = _STATIC_CROSS_LINKS.get((code_a, code_b), [])
    if links:
        return links
    # Try prefix matching (6→4 digit fallback)
    for a_len in range(len(code_a), 3, -1):
        for b_len in range(len(code_b), 3, -1):
            links = _STATIC_CROSS_LINKS.get((code_a[:a_len], code_b[:b_len]), [])
            if links:
                return links
    return []
