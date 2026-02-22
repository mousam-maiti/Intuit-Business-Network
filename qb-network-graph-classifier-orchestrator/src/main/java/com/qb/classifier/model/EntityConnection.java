package com.qb.classifier.model;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

/**
 * One row from Paimon silver.entity_connections.
 * PK: (company_id, connection_id, connection_type)
 *
 * Populated by two Flink streaming jobs:
 *   Job 1 (Identity Sync)  → display_name, ein, contact, category, address, etc.
 *   Job 2 (Transaction Agg) → total_volume, transaction_count, first/last_transaction
 *
 * Paimon's partial-update merge engine combines them on the PK.
 */
public record EntityConnection(
    // ── Keys ──
    long companyId,
    long connectionId,
    String connectionType,          // "vendor" or "customer"

    // ── Identity ──
    String displayName,
    String ein,
    String contactName,
    String email,
    String phone,

    // ── Industry ──
    String category,
    String commodity,

    // ── Location ──
    String streetAddress,
    String city,
    String state,
    String zip,

    // ── Behavioral (from vendor/customer record) ──
    String website,
    BigDecimal expectedVolume,
    String paymentTerms,

    // ── Behavioral (pre-aggregated by Job 2) ──
    BigDecimal totalVolume,
    Long transactionCount,
    LocalDate firstTransaction,
    LocalDate lastTransaction,

    // ── Metadata ──
    LocalDateTime updatedAt
) {
    /** Does this row have identity data (from Job 1)? */
    public boolean hasIdentity() {
        return displayName != null && !displayName.isBlank();
    }

    /** Does this row have transaction data (from Job 2)? */
    public boolean hasTransactions() {
        return totalVolume != null && transactionCount != null;
    }

    /** Natural key for tracking classified state. */
    public String naturalKey() {
        return companyId + ":" + connectionId + ":" + connectionType;
    }
}
