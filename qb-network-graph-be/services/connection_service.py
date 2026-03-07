"""Connection service — reads/writes entity_connections via Paimon."""
from __future__ import annotations

import logging
import math
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from clients.paimon_client import PaimonClient
from repositories.base import AbstractAlertRepository

logger = logging.getLogger(__name__)

# Manual connections use epoch-ms IDs (≥ 1 billion);
# CDC auto-increment IDs from the source DB are always < 1 billion.
_MANUAL_ID_THRESHOLD = 1_000_000_000


def _sanitize_row(row: dict) -> dict:
    """Replace NaN/Inf floats with None so JSON serialization succeeds."""
    return {k: (None if isinstance(v, float) and (math.isnan(v) or math.isinf(v)) else v)
            for k, v in row.items()}


class ConnectionService:
    def __init__(self, paimon: PaimonClient, alert_repo: AbstractAlertRepository,
                 neo4j_driver=None, neo4j_database: str = "neo4j",
                 entity_repo=None, relationship_repo=None):
        self._paimon = paimon
        self._alert_repo = alert_repo
        self._neo4j_driver = neo4j_driver
        self._neo4j_db = neo4j_database
        self._entity_repo = entity_repo
        self._relationship_repo = relationship_repo

    def _neo4j_run(self, cypher: str, params: dict = None) -> list[dict]:
        with self._neo4j_driver.session(database=self._neo4j_db) as session:
            result = session.run(cypher, params or {})
            return [dict(record) for record in result]

    def get_auto(self) -> dict:
        rows = self._paimon.read_table("network_graph.entity_connections")
        return {"data": [_sanitize_row(r) for r in rows if r.get("connection_id", 0) < _MANUAL_ID_THRESHOLD]}

    def get_manual(self) -> dict:
        rows = self._paimon.read_table("network_graph.entity_connections")
        return {"data": [_sanitize_row(r) for r in rows if r.get("connection_id", 0) >= _MANUAL_ID_THRESHOLD]}

    def add(self, payload: dict) -> dict:
        connection_id = int(time.time() * 1000)

        row = {
            "company_id": 1,
            "connection_id": connection_id,
            "connection_type": payload.get("connType"),
            "display_name": payload.get("name"),
            "ein": payload.get("ein"),
            "contact_name": payload.get("contactName"),
            "email": payload.get("email"),
            "phone": payload.get("phone"),
            "category": payload.get("category"),
            "commodity": payload.get("commodity"),
            "street_address": payload.get("address"),
            "city": payload.get("city"),
            "state": payload.get("state"),
            "zip": payload.get("zip"),
            "website": payload.get("website"),
            "expected_volume": Decimal(payload["expectedVolume"]) if payload.get("expectedVolume") else None,
            "payment_terms": payload.get("paymentTerms"),
            "updated_at": datetime.now(timezone.utc),
        }
        self._paimon.write_row("network_graph.entity_connections", row)

        # Create alert for the new connection
        alert_id = f"a-{uuid.uuid4().hex[:8]}"
        entity_name = (
            (payload.get("entity") or {}).get("name")
            if payload.get("entity")
            else payload.get("name")
        )
        self._alert_repo.insert(
            alert_id=alert_id,
            connection_id=connection_id,
            alert_type="connection_added",
            title="Connection added",
            message=f"{entity_name or 'New connection'} added as {payload.get('connType', 'vendor')}. Entity resolution running.",
            entity_name=entity_name,
        )

        return {"id": connection_id, "status": "written"}

    def add_existing(self, golden_record_id: str, conn_type: str, company_id: str = "1") -> dict:
        """Add an existing golden record entity to the user's network.

        Creates a direct Neo4j relationship between the user's entity and the
        target, then returns the target + all its 1-hop neighbors so the UI
        can pull them into the network graph.
        """
        if not self._neo4j_driver:
            return {"error": "Neo4j unavailable", "added": 0}

        # 1. Create relationship between user entity and target
        if conn_type == "vendor":
            # User buys from this entity
            rel_cypher = """
                MATCH (user:Entity {id: $company_id}), (target:Entity {id: $target_id})
                MERGE (user)-[r:BUYS_FROM]->(target)
                ON CREATE SET r.volume = 0, r.count = 0, r.status = 'ACTIVE',
                              r.created_at = datetime()
                RETURN target.canonical_name AS target_name
            """
        else:
            # Entity buys from user (user is the vendor/seller)
            rel_cypher = """
                MATCH (user:Entity {id: $company_id}), (target:Entity {id: $target_id})
                MERGE (target)-[r:BUYS_FROM]->(user)
                ON CREATE SET r.volume = 0, r.count = 0, r.status = 'ACTIVE',
                              r.created_at = datetime()
                RETURN target.canonical_name AS target_name
            """

        result = self._neo4j_run(rel_cypher, {
            "company_id": company_id,
            "target_id": golden_record_id,
        })
        target_name = result[0]["target_name"] if result else golden_record_id

        # 2. Get all 1-hop neighbors of the target entity (these become part of the user's extended network)
        neighbor_cypher = """
            MATCH (target:Entity {id: $target_id})-[r]-(neighbor:Entity)
            WHERE neighbor.status <> 'MERGED' AND neighbor.id <> $company_id
            RETURN DISTINCT neighbor.id AS id, neighbor.canonical_name AS name, type(r) AS rel_type
        """
        neighbors = self._neo4j_run(neighbor_cypher, {
            "target_id": golden_record_id,
            "company_id": company_id,
        })

        # 3. Fetch full entity details for target + neighbors
        neighbor_ids = [n["id"] for n in neighbors]
        all_ids = [golden_record_id] + neighbor_ids

        entities = []
        if self._entity_repo:
            entities = self._entity_repo.batch_fetch(all_ids)

        # 4. Get all edges among these entities
        relationships = []
        if self._relationship_repo:
            relationships = self._relationship_repo._get_edges_between(all_ids + [company_id])

        # 5. Create alert
        alert_id = f"a-{uuid.uuid4().hex[:8]}"
        self._alert_repo.insert(
            alert_id=alert_id,
            connection_id=0,
            alert_type="network_expanded",
            title="Network expanded",
            message=f"{target_name} added as {conn_type}. {len(neighbors)} connected entities joined your network.",
            entity_name=target_name,
            target_entity_id=golden_record_id,
        )

        logger.info(f"Added existing entity {golden_record_id} ({target_name}) as {conn_type} — "
                     f"{len(neighbors)} neighbors pulled into network")

        return {
            "added_entity_id": golden_record_id,
            "added_entity_name": target_name,
            "conn_type": conn_type,
            "neighbor_count": len(neighbors),
            "entities": entities,
            "relationships": relationships,
        }

    def remove_connection(self, entity_id: str, company_id: str = "1") -> dict:
        """Remove relationships between the user's entity and a target.

        Handles both BUYS_FROM and SELLS_TO in either direction,
        including relationships through intermediate QB company nodes.
        """
        if not self._neo4j_driver:
            return {"error": "Neo4j unavailable", "removed": False}

        # 1. Try direct relationship (BUYS_FROM or SELLS_TO in either direction)
        cypher = """
            MATCH (user:Entity {id: $company_id})-[r]-(target:Entity {id: $target_id})
            WHERE type(r) IN ['BUYS_FROM', 'SELLS_TO']
            WITH r, target.canonical_name AS name
            DELETE r
            RETURN name
        """
        result = self._neo4j_run(cypher, {
            "company_id": company_id,
            "target_id": entity_id,
        })

        # 2. If no direct relationship, try via intermediate QB company nodes
        if not result:
            cypher2 = """
                MATCH (user:Entity {id: $company_id})-[:BUYS_FROM|SELLS_TO]-(mid:Entity)-[r:BUYS_FROM|SELLS_TO]-(target:Entity {id: $target_id})
                WHERE mid.entity_type IS NULL OR mid.entity_type <> 'PHANTOM'
                WITH r, target.canonical_name AS name
                DELETE r
                RETURN name
            """
            result = self._neo4j_run(cypher2, {
                "company_id": company_id,
                "target_id": entity_id,
            })

        target_name = result[0]["name"] if result else entity_id
        removed = len(result) > 0

        logger.info(f"Remove connection to {entity_id} ({target_name}): {'success' if removed else 'no relationship found'}")

        return {
            "removed_entity_id": entity_id,
            "removed_entity_name": target_name,
            "removed": removed,
        }
