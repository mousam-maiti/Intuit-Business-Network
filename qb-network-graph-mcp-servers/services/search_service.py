"""
Search service — hybrid search, describe, network queries, aggregate.

Business logic extracted from search_tools.py.
Vector search uses Neo4j native vector indexes.
"""
from __future__ import annotations

import json
import logging
import time

from interfaces.entity_repository import AbstractEntityRepository
from interfaces.relationship_repository import AbstractRelationshipRepository
from interfaces.audit_repository import AbstractAuditRepository
from interfaces.search_repository import AbstractSearchRepository
from interfaces.cache_provider import AbstractCacheProvider
from interfaces.embedding_provider import AbstractEmbeddingProvider

logger = logging.getLogger(__name__)


class SearchService:
    """Entity search, describe, network queries, aggregate, merge history."""

    def __init__(
        self,
        entity_repo: AbstractEntityRepository,
        relationship_repo: AbstractRelationshipRepository,
        audit_repo: AbstractAuditRepository,
        search_repo: AbstractSearchRepository,
        embedding: AbstractEmbeddingProvider,
        cache: AbstractCacheProvider,
    ):
        self._entity_repo = entity_repo
        self._rel_repo = relationship_repo
        self._audit_repo = audit_repo
        self._search_repo = search_repo
        self._embedding = embedding
        self._cache = cache

    def search_entities(
        self, query: str, naics_filter=None, state_filter=None,
        city_filter=None, min_confidence=None, limit: int = 10,
    ) -> dict:
        """Hybrid search: Neo4j name match + Neo4j vector search."""
        results = []
        seen_ids = set()

        # Phase 1: Neo4j fulltext name search
        neo4j_hits = self._search_repo.search_by_name(
            query=query, state_filter=state_filter, city_filter=city_filter,
            naics_filter=naics_filter, min_confidence=min_confidence, limit=limit,
        )
        for hit in neo4j_hits:
            gr_id = hit.get("golden_record_id", "")
            if gr_id and gr_id not in seen_ids:
                seen_ids.add(gr_id)
                results.append({
                    "golden_record_id": gr_id,
                    "canonical_name": hit.get("canonical_name", ""),
                    "state": hit.get("state", ""),
                    "city": hit.get("city", ""),
                    "naics_code": hit.get("naics_code", ""),
                    "naics_sector": hit.get("naics_sector", ""),
                    "confidence": float(hit.get("confidence", 0)),
                    "entity_type": hit.get("entity_type", ""),
                    "source_count": int(hit.get("source_count", 1)),
                    "similarity": float(hit.get("match_rank", 0.9)),
                })

        # Neo4j vector search
        if len(results) < limit:
            try:
                query_vector = self._embedding.embed_text(query)
                if query_vector:
                    vector_hits = self._search_repo.vector_search(
                        query_vector=query_vector,
                        state_filter=state_filter,
                        naics_filter=naics_filter,
                        top_k=limit * 3,
                    )
                    for hit in vector_hits:
                        if len(results) >= limit:
                            break
                        gr_id = hit.get("golden_record_id", "")
                        if not gr_id or gr_id in seen_ids:
                            continue
                        seen_ids.add(gr_id)
                        if city_filter:
                            gr_city = (hit.get("city") or "").upper()
                            if gr_city != city_filter.upper():
                                continue
                        if min_confidence is not None:
                            if float(hit.get("confidence", 0)) < min_confidence:
                                continue
                        results.append({
                            "golden_record_id": gr_id,
                            "canonical_name": hit.get("canonical_name", ""),
                            "state": hit.get("state", ""),
                            "city": hit.get("city", ""),
                            "naics_code": hit.get("naics_code", ""),
                            "naics_sector": hit.get("naics_sector", ""),
                            "confidence": float(hit.get("confidence", 0)),
                            "entity_type": hit.get("entity_type", ""),
                            "source_count": int(hit.get("source_count", 1)),
                            "similarity": hit.get("score", 0.0),
                        })
            except Exception as e:
                logger.warning(f"Neo4j vector search failed, using fulltext results only: {e}")

        return {
            "results": results, "total_found": len(results), "query": query,
            "filters_applied": {
                k: v for k, v in {"state": state_filter, "city": city_filter,
                                   "naics": naics_filter, "min_confidence": min_confidence}.items()
                if v is not None
            },
        }

    def describe_entity(self, entity_id: str) -> dict:
        """Get a full profile of a golden record entity."""
        gr_data = self._entity_repo.get(entity_id)
        if not gr_data:
            return {"error": f"Entity {entity_id} not found", "entity": None}

        persona = gr_data.get("persona", {})
        if isinstance(persona, str):
            try:
                persona = json.loads(persona)
            except (json.JSONDecodeError, TypeError):
                persona = {}

        name_variants = gr_data.get("name_variants", [])
        if isinstance(name_variants, str):
            try:
                name_variants = json.loads(name_variants)
            except (json.JSONDecodeError, TypeError):
                name_variants = []

        profile = {
            "golden_record_id": entity_id,
            "canonical_name": gr_data.get("canonical_name", ""),
            "name_variants": name_variants,
            "status": gr_data.get("status", ""),
            "entity_type": gr_data.get("entity_type", ""),
            "confidence": float(gr_data.get("confidence", 0)),
            "source_count": int(gr_data.get("source_count", 1)),
            "identity": {
                "ein": gr_data.get("ein") or persona.get("identity", {}).get("ein_clean"),
                "phone": gr_data.get("phone_digits") or persona.get("identity", {}).get("phone_digits"),
                "email": gr_data.get("email") or persona.get("identity", {}).get("email"),
            },
            "industry": {
                "naics_code": gr_data.get("naics_code") or persona.get("industry", {}).get("naics_code"),
                "naics_sector": gr_data.get("naics_sector") or persona.get("industry", {}).get("naics_sector"),
                "naics_subsector": gr_data.get("naics_subsector") or persona.get("industry", {}).get("naics_subsector"),
            },
            "location": {
                "state": gr_data.get("state") or persona.get("location", {}).get("state"),
                "city": gr_data.get("city") or persona.get("location", {}).get("city_norm"),
                "zip5": gr_data.get("zip5") or persona.get("location", {}).get("zip5"),
                "zip3": gr_data.get("zip3") or persona.get("location", {}).get("zip3"),
            },
            "commodity": {
                "top_keywords": gr_data.get("commodity_keywords") or persona.get("commodity", {}).get("top_keywords", []),
                "service_categories": gr_data.get("service_categories") or persona.get("commodity", {}).get("service_categories", []),
            },
            "behavioral": {
                "volume_bracket": gr_data.get("volume_bracket") or persona.get("behavioral", {}).get("volume_bracket"),
                "avg_transaction": gr_data.get("avg_transaction") or persona.get("behavioral", {}).get("avg_transaction"),
                "transaction_count": gr_data.get("transaction_count") or persona.get("behavioral", {}).get("transaction_count"),
            },
            "merged_into": gr_data.get("merged_into"),
            "created_at": gr_data.get("created_at"),
            "updated_at": gr_data.get("updated_at"),
        }

        neighbors = []
        if self._entity_repo.available:
            raw_neighbors = self._rel_repo.get_neighbors(entity_id, direction="both")
            for n in raw_neighbors:
                neighbors.append({
                    "entity_id": n.get("id", ""),
                    "name": n.get("name", ""),
                    "rel_type": n.get("rel_type", ""),
                    "volume": float(n.get("volume") or 0),
                })

        return {
            "entity": profile, "neighbors": neighbors,
            "neighbor_count": len(neighbors),
            "neo4j_available": self._entity_repo.available,
        }

    def aggregate_stats(
        self, group_by: str, state_filter=None, naics_filter=None, min_confidence=None,
    ) -> dict:
        """Aggregate golden record statistics by a grouping dimension."""
        groups = self._search_repo.aggregate(
            group_by=group_by, state_filter=state_filter,
            naics_filter=naics_filter, min_confidence=min_confidence,
        )
        if groups and isinstance(groups[0], dict) and "error" in groups[0]:
            return groups[0]
        total = sum(g.get("count", 0) for g in groups)
        return {
            "groups": groups, "total": total, "group_by": group_by,
            "filters_applied": {
                k: v for k, v in {"state": state_filter, "naics": naics_filter,
                                   "min_confidence": min_confidence}.items()
                if v is not None
            },
        }

    def get_merge_history(self, entity_id: str, limit: int = 50) -> dict:
        """Retrieve the merge/resolution audit trail."""
        records = self._audit_repo.get_trail(entity_id, limit=limit)
        merge_count = sum(1 for r in records if r.get("decision") == "MERGE")
        review_count = sum(1 for r in records if r.get("decision") == "REVIEW")
        new_entity_count = sum(1 for r in records if r.get("decision") == "NEW_ENTITY")
        return {
            "entity_id": entity_id, "audit_records": records,
            "total_records": len(records),
            "summary": {"merges": merge_count, "reviews": review_count, "new_entities": new_entity_count},
        }

    def get_company_connections(
        self, company_id: str, connection_type: str = "all",
        sort_by: str = "volume", limit: int = 20,
    ) -> dict:
        """Get vendors/customers for a specific company."""
        rows = self._rel_repo.get_relationships(
            company_id=company_id, connection_type=connection_type,
            sort_by=sort_by, limit=limit,
        )
        connections = []
        total_volume = 0.0
        total_txns = 0
        for r in rows:
            vol = float(r.get("transaction_volume") or 0)
            txn = int(r.get("transaction_count") or 0)
            total_volume += vol
            total_txns += txn
            conn_type = r.get("connection_type", "vendor")
            other_id = r.get("target_entity_id", "") if conn_type == "vendor" else r.get("source_entity_id", "")
            connections.append({
                "golden_record_id": other_id,
                "canonical_name": r.get("canonical_name", ""),
                "state": r.get("state", ""), "city": r.get("city", ""),
                "naics_code": r.get("naics_code", ""),
                "confidence": float(r.get("confidence", 0)),
                "entity_type": r.get("entity_type", ""),
                "source_count": int(r.get("source_count", 1)),
                "transaction_volume": vol, "transaction_count": txn,
                "connection_type": conn_type,
            })
        return {
            "connections": connections, "total": len(connections),
            "company_id": company_id, "connection_type": connection_type, "sort_by": sort_by,
            "summary": {
                "total_volume": round(total_volume, 2),
                "total_transactions": total_txns,
                "avg_volume_per_connection": round(total_volume / len(connections), 2) if connections else 0,
            },
        }
