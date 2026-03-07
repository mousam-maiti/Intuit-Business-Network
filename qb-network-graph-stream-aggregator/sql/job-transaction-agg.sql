-- ============================================================
-- Job 2: Transaction Aggregation (Pre-aggregated)
-- ============================================================
-- Reads staged_bills + staged_invoices changelogs.
-- GROUP BY computes running totals in Flink state.
-- Writes pre-aggregated totals per (company, vendor/customer).
-- Paimon receives the latest total via last_non_null_value.
--
-- Restart-safe: Flink replays snapshot → recomputes same
-- totals → Paimon overwrites with same values.
-- ============================================================

CREATE CATALOG paimon WITH (
    'type' = 'paimon',
    'warehouse' = '${WAREHOUSE_PATH}'
);
USE CATALOG paimon;
USE network_graph;

SET 'execution.runtime-mode' = 'streaming';
SET 'execution.checkpointing.interval' = '30s';
SET 'table.exec.sink.upsert-materialize' = 'NONE';
SET 'parallelism.default' = '1';

INSERT INTO entity_connections
SELECT
    company_id,
    vendor_id                        AS connection_id,
    CAST('vendor' AS STRING)         AS connection_type,

    -- Identity (NULL — preserved by last_non_null_value from Job 1)
    CAST(NULL AS STRING)             AS display_name,
    CAST(NULL AS STRING)             AS ein,
    CAST(NULL AS STRING)             AS contact_name,
    CAST(NULL AS STRING)             AS email,
    CAST(NULL AS STRING)             AS phone,

    CAST(NULL AS STRING)             AS category,
    CAST(NULL AS STRING)             AS commodity,

    CAST(NULL AS STRING)             AS street_address,
    CAST(NULL AS STRING)             AS city,
    CAST(NULL AS STRING)             AS state,
    CAST(NULL AS STRING)             AS zip,

    CAST(NULL AS STRING)             AS website,
    CAST(NULL AS DECIMAL(14, 2))     AS expected_volume,
    CAST(NULL AS STRING)             AS payment_terms,

    -- Pre-aggregated behavioral
    SUM(total)                       AS total_volume,
    COUNT(*)                         AS transaction_count,
    MIN(bill_date)                   AS first_transaction,
    MAX(bill_date)                   AS last_transaction,

    MAX(updated_at)                  AS updated_at

FROM staged_bills /*+ OPTIONS('scan.mode'='latest-full') */
GROUP BY company_id, vendor_id

UNION ALL

SELECT
    company_id,
    customer_id                      AS connection_id,
    CAST('customer' AS STRING)       AS connection_type,

    CAST(NULL AS STRING),
    CAST(NULL AS STRING),
    CAST(NULL AS STRING),
    CAST(NULL AS STRING),
    CAST(NULL AS STRING),

    CAST(NULL AS STRING),
    CAST(NULL AS STRING),

    CAST(NULL AS STRING),
    CAST(NULL AS STRING),
    CAST(NULL AS STRING),
    CAST(NULL AS STRING),

    CAST(NULL AS STRING),
    CAST(NULL AS DECIMAL(14, 2)),
    CAST(NULL AS STRING),

    SUM(total)                       AS total_volume,
    COUNT(*)                         AS transaction_count,
    MIN(invoice_date)                AS first_transaction,
    MAX(invoice_date)                AS last_transaction,

    MAX(updated_at)                  AS updated_at

FROM staged_invoices /*+ OPTIONS('scan.mode'='latest-full') */
GROUP BY company_id, customer_id;
