-- ============================================================
-- Entity Connections — Silver Table DDL
-- ============================================================
--
-- Uses partial-update merge engine:
--   - Non-NULL fields overwrite existing values
--   - NULL fields are skipped (preserves existing)
--   - Retractions/deletes ignored (ignore-delete=true)
--
-- Job 1 writes identity (NULLs for behavioral) → identity preserved
-- Job 2 writes pre-aggregated totals (NULLs for identity) → totals overwrite
-- On restart: same values written → same result (idempotent)
-- ============================================================

CREATE CATALOG paimon WITH (
    'type' = 'paimon',
    'warehouse' = '${WAREHOUSE_PATH}'
);
USE CATALOG paimon;
USE network_graph;

DROP TABLE IF EXISTS entity_connections;

CREATE TABLE entity_connections (

    -- ── Keys ──
    company_id          BIGINT,
    connection_id       BIGINT,
    connection_type     STRING,

    -- ── Identity ──
    display_name        STRING,
    ein                 STRING,
    contact_name        STRING,
    email               STRING,
    phone               STRING,

    -- ── Industry ──
    category            STRING,
    commodity           STRING,

    -- ── Location ──
    street_address      STRING,
    city                STRING,
    state               STRING,
    zip                 STRING,

    -- ── Behavioral (from vendor/customer record) ──
    website             STRING,
    expected_volume     DECIMAL(14, 2),
    payment_terms       STRING,

    -- ── Behavioral (pre-aggregated by Job 2) ──
    total_volume        DECIMAL(14, 2),
    transaction_count   BIGINT,
    first_transaction   DATE,
    last_transaction    DATE,

    -- ── Metadata ──
    updated_at          TIMESTAMP(3),

    PRIMARY KEY (company_id, connection_id, connection_type) NOT ENFORCED

) WITH (
    'merge-engine'                   = 'partial-update',
    'partial-update.ignore-delete'   = 'true',
    'changelog-producer'             = 'none',
    'bucket'                         = '1',
    'snapshot.time-retained'         = '72h',
    'snapshot.num-retained'          = '100'
);
