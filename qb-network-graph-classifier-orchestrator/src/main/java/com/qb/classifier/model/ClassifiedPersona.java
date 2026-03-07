package com.qb.classifier.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * Classified persona — multi-dimensional profile of a business entity.
 * Matches the agent's ClassifiedPersona Pydantic model exactly.
 *
 * @see agent-service/models/persona.py
 */
@JsonInclude(JsonInclude.Include.ALWAYS)
public record ClassifiedPersona(
    IdentityDimension identity,
    IndustryDimension industry,
    LocationDimension location,
    CommodityDimension commodity,
    BehavioralDimension behavioral,
    SparsityScores sparsity
) {

    // ── Identity ──────────────────────────────────────────────

    @JsonInclude(JsonInclude.Include.ALWAYS)
    public record IdentityDimension(
        @JsonProperty("canonical_name")   String normalizedName,
        @JsonProperty("name_first_token") String nameFirstToken,
        @JsonProperty("name_tokens")      List<String> nameTokens,
        @JsonProperty("legal_suffix")     String legalSuffix,
        @JsonProperty("ein_clean")        String einClean,
        @JsonProperty("phone_digits")     String phoneDigits,
        @JsonProperty("email")            String email,
        @JsonProperty("email_domain")     String emailDomain
    ) {}

    // ── Industry ──────────────────────────────────────────────

    @JsonInclude(JsonInclude.Include.ALWAYS)
    public record IndustryDimension(
        @JsonProperty("naics_code")          String naicsCode,
        @JsonProperty("naics_sector")        String naicsSector,
        @JsonProperty("naics_subsector")     String naicsSubsector,
        @JsonProperty("original_category")   String originalCategory,
        @JsonProperty("commodity_keywords")  List<String> commodityKeywords
    ) {}

    // ── Location ──────────────────────────────────────────────

    @JsonInclude(JsonInclude.Include.ALWAYS)
    public record LocationDimension(
        @JsonProperty("state")     String state,
        @JsonProperty("city_norm") String cityNorm,
        @JsonProperty("zip3")      String zip3,
        @JsonProperty("zip5")      String zip5
    ) {}

    // ── Commodity ─────────────────────────────────────────────

    @JsonInclude(JsonInclude.Include.ALWAYS)
    public record CommodityDimension(
        @JsonProperty("top_keywords")       List<String> topKeywords,
        @JsonProperty("service_categories") List<String> serviceCategories
    ) {}

    // ── Behavioral ────────────────────────────────────────────

    @JsonInclude(JsonInclude.Include.ALWAYS)
    public record BehavioralDimension(
        @JsonProperty("volume_bracket")    String volumeBracket,
        @JsonProperty("avg_transaction")   Double avgTransaction,
        @JsonProperty("transaction_count") Integer transactionCount,
        @JsonProperty("payment_terms")     String paymentTerms
    ) {}

    // ── Sparsity ──────────────────────────────────────────────

    @JsonInclude(JsonInclude.Include.ALWAYS)
    public record SparsityScores(
        int identity,
        int industry,
        int location,
        int commodity,
        int behavioral
    ) {}
}
