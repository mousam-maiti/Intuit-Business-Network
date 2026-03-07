"""
Sync service — push resolved data from Paimon gold to Neo4j + Redis.

Called by the Classifier Orchestrator after writing to Paimon gold.
Reuses existing Neo4j upsert/create/write methods and Redis invalidation.
Generates embeddings for vector search on Neo4j Entity nodes.
"""
from __future__ import annotations

import logging

from interfaces.entity_repository import AbstractEntityRepository
from interfaces.relationship_repository import AbstractRelationshipRepository
from interfaces.audit_repository import AbstractAuditRepository
from interfaces.cache_provider import AbstractCacheProvider
from interfaces.embedding_provider import AbstractEmbeddingProvider

logger = logging.getLogger(__name__)


class SyncService:
    """Sync Paimon gold records to Neo4j serving layer + Redis cache."""

    def __init__(
        self,
        entity_repo: AbstractEntityRepository,
        relationship_repo: AbstractRelationshipRepository,
        audit_repo: AbstractAuditRepository,
        cache: AbstractCacheProvider,
        embedding: AbstractEmbeddingProvider = None,
    ):
        self._entity_repo = entity_repo
        self._rel_repo = relationship_repo
        self._audit_repo = audit_repo
        self._cache = cache
        self._embedding = embedding

    async def sync_golden_record(self, golden_record: dict) -> dict:
        """Upsert a golden record to Neo4j (with embedding) and invalidate Redis cache."""
        gr_id = golden_record.get("golden_record_id", "")
        try:
            # Generate embedding for vector search
            if self._embedding:
                embedding_text = self._build_embedding_text(golden_record)
                if embedding_text:
                    embedding_vec = self._embedding.embed_text(embedding_text)
                    if embedding_vec:
                        golden_record["embedding"] = embedding_vec

            self._entity_repo.upsert(golden_record)
            await self._cache.invalidate_entity(gr_id)
            logger.info(f"Synced golden record {gr_id} to Neo4j")
            return {"success": True, "golden_record_id": gr_id}
        except Exception as e:
            logger.error(f"Failed to sync golden record {gr_id}: {e}")
            return {"success": False, "error": str(e)}

    def _build_embedding_text(self, gr: dict) -> str:
        """Build text representation for embedding from golden record fields."""
        parts = []
        name = gr.get("canonical_name") or ""
        if name:
            parts.append(name)
        persona = gr.get("persona") or {}
        if isinstance(persona, str):
            import json
            try:
                persona = json.loads(persona)
            except (json.JSONDecodeError, TypeError):
                persona = {}
        industry = persona.get("industry", {})
        if industry.get("original_category"):
            parts.append(industry["original_category"])
        location = persona.get("location", {})
        loc_parts = [location.get("city_norm", ""), location.get("state", "")]
        loc = " ".join(p for p in loc_parts if p)
        if loc:
            parts.append(loc)
        commodity = persona.get("commodity", {})
        keywords = commodity.get("top_keywords", [])
        if keywords:
            parts.append(" ".join(keywords[:5]))
        return " | ".join(parts) if parts else ""

    async def sync_relationship(self, relationship: dict) -> dict:
        """Create a relationship edge in Neo4j."""
        edge_id = relationship.get("edge_id", "")
        try:
            self._rel_repo.create(
                source_id=relationship["source_entity_id"],
                target_id=relationship["target_entity_id"],
                rel_type=relationship["rel_type"],
                properties={
                    "volume": relationship.get("transaction_volume"),
                    "count": relationship.get("transaction_count"),
                    "edge_id": edge_id,
                },
            )
            # Invalidate cache for both endpoints
            await self._cache.invalidate_entity(relationship["source_entity_id"])
            await self._cache.invalidate_entity(relationship["target_entity_id"])
            logger.info(f"Synced relationship {edge_id} to Neo4j")
            return {"success": True, "edge_id": edge_id}
        except Exception as e:
            logger.error(f"Failed to sync relationship {edge_id}: {e}")
            return {"success": False, "error": str(e)}

    async def sync_audit(self, audit: dict) -> dict:
        """Create an audit entry node in Neo4j."""
        audit_id = audit.get("audit_id", "")
        try:
            self._audit_repo.write(audit)
            logger.info(f"Synced audit {audit_id} to Neo4j")
            return {"success": True, "audit_id": audit_id}
        except Exception as e:
            logger.error(f"Failed to sync audit {audit_id}: {e}")
            return {"success": False, "error": str(e)}

    async def transfer_relationships(self, absorbed_id: str, survivor_id: str) -> dict:
        """Transfer all relationships from absorbed entity to survivor after a merge.

        Re-points edges from absorbed → survivor, then marks absorbed as MERGED.
        """
        try:
            self._rel_repo.merge_entities(survivor_id, absorbed_id)
            await self._cache.invalidate_entity(absorbed_id)
            await self._cache.invalidate_entity(survivor_id)
            logger.info(f"Transferred relationships from {absorbed_id} to {survivor_id}")
            return {"success": True, "absorbed_id": absorbed_id, "survivor_id": survivor_id}
        except Exception as e:
            logger.error(f"Failed to transfer relationships {absorbed_id} → {survivor_id}: {e}")
            return {"success": False, "error": str(e)}

    async def backfill_embeddings(self) -> dict:
        """Backfill embeddings for all entities that lack them."""
        if not self._embedding:
            return {"success": False, "error": "No embedding provider configured"}

        all_entities = self._entity_repo.get_all(active_only=True)
        total = 0
        embedded = 0
        skipped = 0
        errors = 0

        for entity in all_entities:
            total += 1
            # Skip entities that already have embeddings
            if entity.get("embedding"):
                skipped += 1
                continue
            try:
                embedding_text = self._build_embedding_text(entity)
                if not embedding_text:
                    skipped += 1
                    continue
                embedding_vec = self._embedding.embed_text(embedding_text)
                if not embedding_vec:
                    skipped += 1
                    continue
                entity["embedding"] = embedding_vec
                self._entity_repo.upsert(entity)
                embedded += 1
            except Exception as e:
                logger.error(f"Backfill embedding failed for {entity.get('golden_record_id')}: {e}")
                errors += 1

        logger.info(f"Backfill complete: {embedded} embedded, {skipped} skipped, {errors} errors out of {total}")
        return {
            "success": True,
            "total": total,
            "embedded": embedded,
            "skipped": skipped,
            "errors": errors,
        }

    async def sync_pending_resolution(self, pending: dict) -> dict:
        """Create a pending resolution as a provisional entity in Neo4j."""
        match_id = pending.get("match_id", "")
        try:
            # The provisional golden record is already synced via sync_golden_record.
            # This just logs the pending resolution metadata.
            logger.info(f"Pending resolution {match_id} acknowledged")
            return {"success": True, "match_id": match_id}
        except Exception as e:
            logger.error(f"Failed to sync pending resolution {match_id}: {e}")
            return {"success": False, "error": str(e)}

    async def backfill_relationship_volumes(self) -> dict:
        """Backfill relationship edge volumes from entity behavioral data.

        When the classifier runs before Job 2 (Transaction Aggregation)
        completes, relationship edges get volume=0. This reads each entity's
        avg_transaction * transaction_count and updates the connected edge.
        Also sets total_volume on entity nodes.
        """
        try:
            updated_edges = self._rel_repo.backfill_volumes_from_entities()
            updated_entities = self._entity_repo.backfill_total_volumes()
            logger.info(f"Backfill complete: {updated_edges} edges, {updated_entities} entities updated")
            return {
                "success": True,
                "edges_updated": updated_edges,
                "entities_updated": updated_entities,
            }
        except Exception as e:
            logger.error(f"Backfill relationship volumes failed: {e}")
            return {"success": False, "error": str(e)}
