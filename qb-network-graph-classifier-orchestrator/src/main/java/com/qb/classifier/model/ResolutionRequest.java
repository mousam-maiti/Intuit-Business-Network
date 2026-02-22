package com.qb.classifier.model;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Request body for POST /resolve on the Entity Resolution Agent.
 * Matches design doc §5.2 API contract.
 */
public record ResolutionRequest(
    @JsonProperty("event_id")            String eventId,
    @JsonProperty("record_id")           String recordId,
    @JsonProperty("record_type")         String recordType,
    @JsonProperty("company_id")          Long companyId,
    @JsonProperty("chain_depth")         int chainDepth,
    @JsonProperty("classified_persona")  ClassifiedPersona classifiedPersona
) {

    /**
     * Build a resolution request from an entity connection and its classified persona.
     */
    public static ResolutionRequest from(EntityConnection conn, ClassifiedPersona persona) {
        String eventId = "evt-" + conn.companyId() + "-" + conn.connectionId();
        String recordId = (conn.connectionType().equals("vendor") ? "v-" : "c-") + conn.connectionId();

        return new ResolutionRequest(
            eventId,
            recordId,
            conn.connectionType(),
            conn.companyId(),
            0,
            persona
        );
    }
}
