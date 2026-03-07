package com.qb.classifier.exception;

/**
 * Thrown when classification of an entity connection fails.
 */
public class ClassificationException extends AppException {

    public ClassificationException(String message) {
        super(message, "CLASSIFICATION_ERROR");
    }

    public ClassificationException(String message, Throwable cause) {
        super(message, "CLASSIFICATION_ERROR", cause);
    }
}
