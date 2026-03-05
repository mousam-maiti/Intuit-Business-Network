package com.qb.classifier.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.qb.classifier.classifier.PersonaBuilder;
import com.qb.classifier.client.ResolutionClient;
import com.qb.classifier.client.SyncClient;
import com.qb.classifier.model.ClassifiedPersona;
import com.qb.classifier.model.EntityConnection;
import com.qb.classifier.model.ResolutionRequest;
import com.qb.classifier.stream.ResolvedEntitySink;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
/**
 * Core orchestration service: classify -> resolve -> write to Paimon -> sync to Neo4j.
 *
 * Composes {@link PersonaBuilder}, {@link ResolutionClient},
 * {@link ResolvedEntitySink}, and {@link SyncClient} via constructor injection.
 */
public class ClassificationService {

    private static final Logger log = LoggerFactory.getLogger(ClassificationService.class);
    private static final ObjectMapper JSON = new ObjectMapper();

    private final PersonaBuilder personaBuilder;
    private final ResolutionClient resolutionClient;
    private final ResolvedEntitySink sink;
    private final SyncClient syncClient;
    private boolean fastMode = false;
    private boolean twoPass = true;

    /** Counters for two-pass tracking. */
    private int fastPassResolved = 0;
    private int fullPassFallbacks = 0;

    public ClassificationService(
            PersonaBuilder personaBuilder,
            ResolutionClient resolutionClient,
            ResolvedEntitySink sink,
            SyncClient syncClient) {
        this.personaBuilder = personaBuilder;
        this.resolutionClient = resolutionClient;
        this.sink = sink;
        this.syncClient = syncClient;
    }

    /**
     * Enable fast-only mode — deterministic only, parks ambiguous as REVIEW.
     * Use for batch pass-1 workflow ({@code --fast}).
     * When false (default), two-pass is used: fast first, full fallback.
     */
    public void setFastMode(boolean fastMode) {
        this.fastMode = fastMode;
    }

    /**
     * Enable/disable automatic two-pass per record.
     * Default true: fast pass first, full pass if REVIEW.
     * Set to false to disable (e.g. when --fast is used for batch pass-1 only).
     */
    public void setTwoPass(boolean twoPass) {
        this.twoPass = twoPass;
    }

    public int getFastPassResolved() { return fastPassResolved; }
    public int getFullPassFallbacks() { return fullPassFallbacks; }

    /**
     * Classify an entity connection and return the persona (no resolution).
     */
    public ClassifiedPersona classify(EntityConnection conn) {
        return personaBuilder.build(conn);
    }

    /**
     * Full pipeline: classify -> resolve -> write to gold.
     *
     * Two-pass behavior (default, used in streaming):
     *   1. Fast pass (deterministic only, no embedding/LLM)
     *   2. If REVIEW → full pass (embedding + LLM for ambiguous)
     *
     * Fast-only mode ({@code --fast}): only pass 1, parks ambiguous as REVIEW.
     *
     * @return the agent response body, or null on failure
     */
    public String classifyAndResolve(EntityConnection conn) {
        ClassifiedPersona persona = personaBuilder.build(conn);

        // ── Pass 1: fast deterministic ──────────────────────────
        ResolutionRequest fastRequest = ResolutionRequest.from(conn, persona, true);
        String response = resolutionClient.resolve(fastRequest);

        if (response != null && twoPass && !fastMode && isReviewDecision(response)) {
            // Fast pass returned REVIEW (dry — no store writes).
            // Retry with full resolution (embedding + LLM).
            log.debug("Fast pass deferred {} — retrying with full resolution", conn.displayName());
            ResolutionRequest fullRequest = ResolutionRequest.from(conn, persona, false);
            String fullResponse = resolutionClient.resolve(fullRequest);
            if (fullResponse != null) {
                response = fullResponse;
                fullPassFallbacks++;
            }
        } else if (response != null) {
            fastPassResolved++;
        }

        if (response != null && sink.isAvailable()) {
            writeToGold(conn, response);
        }

        if (log.isDebugEnabled() && response != null) {
            log.debug("[{}] {} -> {} | identity={} industry={} location={} commodity={} behavioral={}",
                conn.connectionType(),
                conn.displayName(),
                persona.identity().normalizedName(),
                persona.sparsity().identity(),
                persona.sparsity().industry(),
                persona.sparsity().location(),
                persona.sparsity().commodity(),
                persona.sparsity().behavioral()
            );
        }

        return response;
    }

    private boolean isReviewDecision(String response) {
        try {
            JsonNode node = JSON.readTree(response);
            JsonNode decision = node.get("decision");
            return decision != null && "REVIEW".equals(decision.asText());
        } catch (Exception e) {
            return false;
        }
    }

    private void writeToGold(EntityConnection conn, String response) {
        try {
            JsonNode responseJson = JSON.readTree(response);

            // 1. Write to Paimon gold (source of truth)
            JsonNode grAfter = responseJson.get("golden_record_after");
            if (grAfter != null && !grAfter.isNull()) {
                sink.writeGoldenRecord(grAfter);
            }

            JsonNode relationship = responseJson.get("relationship");
            if (relationship != null && !relationship.isNull()) {
                sink.writeRelationship(relationship);
            }

            JsonNode audit = responseJson.get("audit_record");
            if (audit != null && !audit.isNull()) {
                sink.writeAudit(audit);
            }

            JsonNode pendingResolution = responseJson.get("pending_resolution");
            if (pendingResolution != null && !pendingResolution.isNull()) {
                sink.writePendingResolution(pendingResolution);
            }

            // 2. Sync to Neo4j serving layer via MCP sync API
            if (syncClient != null) {
                syncToNeo4j(responseJson);
            }
        } catch (Exception e) {
            log.warn("Failed to write to Paimon gold for {}: {}",
                conn.displayName(), e.getMessage());
        }
    }

    private void syncToNeo4j(JsonNode responseJson) {
        try {
            JsonNode grAfter = responseJson.get("golden_record_after");
            if (grAfter != null && !grAfter.isNull()) {
                syncClient.syncGoldenRecord(grAfter);
            }

            JsonNode relationship = responseJson.get("relationship");
            if (relationship != null && !relationship.isNull()) {
                syncClient.syncRelationship(relationship);
            }

            JsonNode audit = responseJson.get("audit_record");
            if (audit != null && !audit.isNull()) {
                syncClient.syncAudit(audit);
            }

            JsonNode pendingResolution = responseJson.get("pending_resolution");
            if (pendingResolution != null && !pendingResolution.isNull()) {
                syncClient.syncPendingResolution(pendingResolution);
            }
        } catch (Exception e) {
            log.warn("Neo4j sync failed (non-fatal, Paimon is source of truth): {}", e.getMessage());
        }
    }
}
