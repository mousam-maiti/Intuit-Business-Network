package com.qb.classifier.stream;

import com.qb.classifier.model.EntityConnection;

import java.util.function.Consumer;

/**
 * Contract for reading EntityConnection rows from a data source.
 */
public interface EntityConnectionSource {

    /**
     * Read all rows (batch/snapshot mode).
     * @return total rows processed
     */
    int readAll(Consumer<EntityConnection> processor) throws Exception;

    /**
     * Stream changelog rows continuously (blocks until interrupted).
     */
    void streamChanges(Consumer<EntityConnection> processor) throws Exception;

    /** Delete the stream checkpoint so the next run starts from the beginning. */
    void clearCheckpoint();
}
