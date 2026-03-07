package com.qb.classifier.client.impl;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.qb.classifier.client.SyncClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/**
 * HTTP implementation of {@link SyncClient}.
 * POSTs golden records, relationships, and audits to the MCP sync API
 * which pushes them to Neo4j + Redis.
 */
public class HttpSyncClient implements SyncClient {

    private static final Logger log = LoggerFactory.getLogger(HttpSyncClient.class);
    private static final ObjectMapper JSON = new ObjectMapper();

    private final String baseUrl;
    private final HttpClient httpClient;

    public HttpSyncClient(String baseUrl) {
        this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();
    }

    @Override
    public boolean syncGoldenRecord(JsonNode goldenRecord) {
        return post("/sync/golden-record", goldenRecord);
    }

    @Override
    public boolean syncRelationship(JsonNode relationship) {
        return post("/sync/relationship", relationship);
    }

    @Override
    public boolean syncAudit(JsonNode audit) {
        return post("/sync/audit", audit);
    }

    @Override
    public boolean syncPendingResolution(JsonNode pending) {
        return post("/sync/pending-resolution", pending);
    }

    private boolean post(String path, JsonNode body) {
        try {
            String json = JSON.writeValueAsString(body);
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + path))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(json))
                    .timeout(Duration.ofSeconds(10))
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() >= 200 && response.statusCode() < 300) {
                log.debug("Sync OK: POST {} -> {}", path, response.statusCode());
                return true;
            } else {
                log.warn("Sync failed: POST {} -> {} {}", path, response.statusCode(), response.body());
                return false;
            }
        } catch (Exception e) {
            log.warn("Sync error: POST {} -> {}", path, e.getMessage());
            return false;
        }
    }
}
