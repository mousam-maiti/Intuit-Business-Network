package com.qb.classifier.exception;

/**
 * Base exception for the classifier-orchestrator.
 */
public class AppException extends RuntimeException {

    private final String code;

    public AppException(String message) {
        this(message, "INTERNAL_ERROR");
    }

    public AppException(String message, String code) {
        super(message);
        this.code = code;
    }

    public AppException(String message, String code, Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
