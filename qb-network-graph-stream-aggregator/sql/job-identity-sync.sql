-- ============================================================
-- Job 1: Identity Sync
-- ============================================================
-- Reads staged_vendors + staged_customers changelogs.
-- Writes all record-level fields; NULLs for transaction aggregates.
-- Restart-safe: last_non_null_value just overwrites with same data.
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

    display_name,
    ein,
    contact_name,
    email,
    phone,

    category,
    commodity,

    street_address,
    city,
    state,
    zip,

    website,
    expected_volume,
    payment_terms,

    CAST(NULL AS DECIMAL(14, 2))     AS total_volume,
    CAST(NULL AS BIGINT)             AS transaction_count,
    CAST(NULL AS DATE)               AS first_transaction,
    CAST(NULL AS DATE)               AS last_transaction,

    updated_at

FROM staged_vendors /*+ OPTIONS('scan.mode'='latest-full') */

UNION ALL

SELECT
    company_id,
    customer_id                      AS connection_id,
    CAST('customer' AS STRING)       AS connection_type,

    display_name,
    ein,
    contact_name,
    email,
    phone,

    category,
    commodity,

    street_address,
    city,
    state,
    zip,

    website,
    expected_volume,
    payment_terms,

    CAST(NULL AS DECIMAL(14, 2)),
    CAST(NULL AS BIGINT),
    CAST(NULL AS DATE),
    CAST(NULL AS DATE),

    updated_at

FROM staged_customers /*+ OPTIONS('scan.mode'='latest-full') */;
