package com.qb.classifier.stream;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * Contract for writing resolved entity data to a persistent store.
 */
public interface ResolvedEntitySink {

    /** Whether this sink is available for writes. */
    boolean isAvailable();

    /** Write a golden record. */
    void writeGoldenRecord(JsonNode goldenRecord);

    /** Write a relationship edge. */
    void writeRelationship(JsonNode relationship);

    /** Write an audit entry. */
    void writeAudit(JsonNode audit);

    /** Write a pending resolution to the gold layer. */
    void writePendingResolution(JsonNode pendingResolution);
}
