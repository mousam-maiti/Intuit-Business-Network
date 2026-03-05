package com.qb.classifier.client;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * Contract for syncing Paimon gold data to the Neo4j serving layer
 * via the MCP sync HTTP endpoints.
 */
public interface SyncClient {

    /** Sync a golden record to Neo4j + invalidate Redis. */
    boolean syncGoldenRecord(JsonNode goldenRecord);

    /** Sync a relationship edge to Neo4j. */
    boolean syncRelationship(JsonNode relationship);

    /** Sync an audit entry to Neo4j. */
    boolean syncAudit(JsonNode audit);

    /** Sync a pending resolution (provisional entity). */
    boolean syncPendingResolution(JsonNode pending);
}
