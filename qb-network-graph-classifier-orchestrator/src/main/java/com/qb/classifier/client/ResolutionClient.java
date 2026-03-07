package com.qb.classifier.client;

import com.qb.classifier.model.ResolutionRequest;

/**
 * Contract for sending classified entities to the Entity Resolution Agent.
 */
public interface ResolutionClient extends AutoCloseable {

    /** POST a resolution request. Returns the response body, or null on failure. */
    String resolve(ResolutionRequest request);

    /** Health check — returns true if the agent service is reachable. */
    boolean healthCheck();

    int getSent();
    int getSucceeded();
    int getFailed();
    int getSkipped();

    String stats();
}
