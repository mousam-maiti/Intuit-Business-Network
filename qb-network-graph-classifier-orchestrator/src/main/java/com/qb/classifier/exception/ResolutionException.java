package com.qb.classifier.exception;

/**
 * Thrown when communication with the Entity Resolution Agent fails.
 */
public class ResolutionException extends AppException {

    public ResolutionException(String message) {
        super(message, "RESOLUTION_ERROR");
    }

    public ResolutionException(String message, Throwable cause) {
        super(message, "RESOLUTION_ERROR", cause);
    }
}
