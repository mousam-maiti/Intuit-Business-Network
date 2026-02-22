package com.qb.classifier.client;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.qb.classifier.model.ResolutionRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

/**
 * HTTP client for the Entity Resolution Agent service.
 * Sends POST /resolve with ClassifiedPersona payloads.
 * Retries transient failures with exponential backoff.
 */
public class AgentClient implements AutoCloseable {

    private static final Logger log = LoggerFactory.getLogger(AgentClient.class);

    private static final int MAX_RETRIES = 3;
    private static final long INITIAL_BACKOFF_MS = 500;

    /** Dead letter envelope — captures the request plus the failure reason. */
    public record DeadLetter(
        String timestamp,
        int httpStatus,
        String errorType,
        String errorMessage,
        String responseBody,
        ResolutionRequest request
    ) {}

    private final String baseUrl;
    private final HttpClient http;
    private final ObjectMapper json;
    private final boolean dryRun;
    private final int timeoutMs;
    private Consumer<DeadLetter> deadLetterSink;

    private final AtomicInteger sent = new AtomicInteger();
    private final AtomicInteger succeeded = new AtomicInteger();
    private final AtomicInteger failed = new AtomicInteger();
    private final AtomicInteger skipped = new AtomicInteger();

    public AgentClient(String baseUrl, int timeoutMs, boolean dryRun) {
        this.baseUrl = baseUrl;
        this.dryRun = dryRun;
        this.timeoutMs = timeoutMs;
        this.http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(timeoutMs))
            .build();
        this.json = new ObjectMapper()
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
    }

    /** Set a callback for requests that fail after all retries. */
    public void setDeadLetterSink(Consumer<DeadLetter> sink) {
        this.deadLetterSink = sink;
    }

    /**
     * POST /resolve with a resolution request.
     * Retries up to MAX_RETRIES times with exponential backoff on transient failures.
     * Returns the response body string, or null on failure.
     */
    public String resolve(ResolutionRequest request) {
        if (dryRun) {
            skipped.incrementAndGet();
            log.debug("DRY RUN: would POST /resolve for {}", request.recordId());
            return "{\"dry_run\": true}";
        }

        String body;
        try {
            body = json.writeValueAsString(request);
        } catch (Exception e) {
            failed.incrementAndGet();
            log.error("Failed to serialize request for {}: {}", request.recordId(), e.getMessage());
            sendToDeadLetter(request, 0, "SERIALIZATION_ERROR", e.getMessage(), null);
            return null;
        }

        sent.incrementAndGet();

        int lastStatus = 0;
        String lastErrorType = "UNKNOWN";
        String lastErrorMessage = null;
        String lastResponseBody = null;

        for (int attempt = 1; attempt <= MAX_RETRIES; attempt++) {
            try {
                HttpRequest httpReq = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/resolve"))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body))
                    .timeout(Duration.ofMillis(timeoutMs))
                    .build();

                HttpResponse<String> resp = http.send(httpReq, HttpResponse.BodyHandlers.ofString());

                if (resp.statusCode() >= 200 && resp.statusCode() < 300) {
                    succeeded.incrementAndGet();
                    log.debug("Agent response for {}: {}", request.recordId(),
                        resp.body().substring(0, Math.min(200, resp.body().length())));
                    return resp.body();
                }

                lastStatus = resp.statusCode();
                lastResponseBody = resp.body();

                // Non-retryable client error (4xx)
                if (resp.statusCode() >= 400 && resp.statusCode() < 500) {
                    failed.incrementAndGet();
                    lastErrorType = "CLIENT_ERROR";
                    lastErrorMessage = "HTTP " + resp.statusCode();
                    log.warn("Agent returned {} for {} (not retryable): {}", resp.statusCode(),
                        request.recordId(), resp.body().substring(0, Math.min(200, resp.body().length())));
                    sendToDeadLetter(request, lastStatus, lastErrorType, lastErrorMessage, lastResponseBody);
                    return null;
                }

                // Server error (5xx) — retryable
                lastErrorType = "SERVER_ERROR";
                lastErrorMessage = "HTTP " + resp.statusCode();
                log.warn("Agent returned {} for {} (attempt {}/{})", resp.statusCode(),
                    request.recordId(), attempt, MAX_RETRIES);

            } catch (Exception e) {
                lastErrorType = e.getClass().getSimpleName();
                lastErrorMessage = e.getMessage();
                log.warn("Failed to call agent for {} (attempt {}/{}): {}",
                    request.recordId(), attempt, MAX_RETRIES, e.getMessage());
            }

            // Backoff before retry
            if (attempt < MAX_RETRIES) {
                try {
                    long backoff = INITIAL_BACKOFF_MS * (1L << (attempt - 1));
                    Thread.sleep(backoff);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        }

        failed.incrementAndGet();
        log.error("All {} retries exhausted for {}", MAX_RETRIES, request.recordId());
        sendToDeadLetter(request, lastStatus, lastErrorType, lastErrorMessage, lastResponseBody);
        return null;
    }

    private void sendToDeadLetter(ResolutionRequest request, int httpStatus,
                                   String errorType, String errorMessage, String responseBody) {
        if (deadLetterSink != null) {
            try {
                DeadLetter dl = new DeadLetter(
                    Instant.now().toString(),
                    httpStatus,
                    errorType,
                    errorMessage,
                    responseBody,
                    request
                );
                deadLetterSink.accept(dl);
            } catch (Exception e) {
                log.warn("Failed to write dead letter for {}: {}", request.recordId(), e.getMessage());
            }
        }
    }

    /**
     * Health check — GET /health.
     */
    public boolean healthCheck() {
        try {
            HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/health"))
                .GET()
                .timeout(Duration.ofSeconds(3))
                .build();

            HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
            return resp.statusCode() == 200;
        } catch (Exception e) {
            return false;
        }
    }

    public int getSent() { return sent.get(); }
    public int getSucceeded() { return succeeded.get(); }
    public int getFailed() { return failed.get(); }
    public int getSkipped() { return skipped.get(); }

    public String stats() {
        return String.format("sent=%d, succeeded=%d, failed=%d, skipped=%d",
            sent.get(), succeeded.get(), failed.get(), skipped.get());
    }

    @Override
    public void close() {
        // HttpClient doesn't need explicit close in Java 11+
    }
}
