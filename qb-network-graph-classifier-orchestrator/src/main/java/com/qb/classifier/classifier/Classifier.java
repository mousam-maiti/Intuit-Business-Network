package com.qb.classifier.classifier;

import com.qb.classifier.model.EntityConnection;

/**
 * Contract for a dimension classifier.
 *
 * Each implementation classifies a single persona dimension
 * (identity, industry, location, commodity, behavioral) from
 * a raw {@link EntityConnection}.
 *
 * @param <T> the typed result of classification
 */
public interface Classifier<T> {

    /** Classify the given entity connection into a typed result. */
    T classify(EntityConnection input);

    /** Human-readable dimension name (e.g. "identity", "industry"). */
    String dimensionName();
}
