-- ============================================================
-- Step 6: Paimon Gold Layer Tables
--
-- Entity resolution output: golden records, relationships,
-- and audit trail. Written by the classifier orchestrator
-- after each /resolve response.
--
-- These tables serve as the compliance/time-travel archive.
-- Neo4j is the real-time primary store.
-- ============================================================

USE CATALOG paimon;

-- Create gold database (separate from bronze/silver network_graph)
CREATE DATABASE IF NOT EXISTS gold;
USE gold;

-- ── Golden Records ─────────────────────────────────────────
-- Resolved entity profiles with 30+ fields.
-- deduplicate merge engine → UPSERT semantics on golden_record_id.
-- Daily auto-tags for time-travel queries.

CREATE TABLE IF NOT EXISTS golden_records (
    golden_record_id   STRING,
    canonical_name     STRING,
    name_variants      STRING,           -- JSON array
    ein                STRING,
    phone_digits       STRING,
    email              STRING,
    email_domain       STRING,
    contact_name       STRING,
    naics_code         STRING,
    naics_sector       STRING,
    naics_subsector    STRING,
    state              STRING,
    city               STRING,
    zip5               STRING,
    zip3               STRING,
    street_address     STRING,
    commodity_keywords STRING,           -- JSON array
    service_categories STRING,           -- JSON array
    total_volume       DECIMAL(14, 2),
    avg_transaction    DECIMAL(12, 2),
    transaction_count  INT,
    volume_bracket     STRING,
    source_count       INT,
    source_records     STRING,           -- JSON array
    confidence         DECIMAL(4, 3),
    status             STRING,           -- ACTIVE | PROVISIONAL | MERGED
    merged_into        STRING,
    entity_type        STRING,           -- QB_USER | PHANTOM
    persona            STRING,           -- JSON object (full classified persona)
    bucket_keys        STRING,           -- JSON array
    created_at         TIMESTAMP(3),
    updated_at         TIMESTAMP(3),
    PRIMARY KEY (golden_record_id) NOT ENFORCED
) WITH (
    'merge-engine'               = 'deduplicate',
    'bucket'                     = '4',
    'tag.automatic-creation'     = 'watermark',
    'tag.num-retained-max'       = '365',
    'snapshot.time-retained'     = '168h',
    'snapshot.num-retained'      = '200'
);

-- ── Relationships ──────────────────────────────────────────
-- Directed edges between golden records (BUYS_FROM / SELLS_TO).

CREATE TABLE IF NOT EXISTS relationships (
    edge_id            STRING,
    source_entity_id   STRING,
    target_entity_id   STRING,
    rel_type           STRING,           -- BUYS_FROM | SELLS_TO
    transaction_volume DECIMAL(14, 2),
    transaction_count  INT,
    created_at         TIMESTAMP(3),
    updated_at         TIMESTAMP(3),
    PRIMARY KEY (edge_id) NOT ENFORCED
) WITH (
    'merge-engine'               = 'deduplicate',
    'bucket'                     = '4',
    'tag.automatic-creation'     = 'watermark',
    'tag.num-retained-max'       = '365',
    'snapshot.time-retained'     = '168h',
    'snapshot.num-retained'      = '200'
);

-- ── Pending Resolution ───────────────────────────────────────
-- Human review work queue. Replaces MySQL pending_resolution table.
-- deduplicate merge engine → UPSERT on match_id (status updates).

CREATE TABLE IF NOT EXISTS pending_resolution (
    match_id             STRING,
    orphan_golden_id     STRING,
    candidate_golden_id  STRING,
    confidence           DECIMAL(4, 3),
    dimension_scores     STRING,           -- JSON object
    reasoning            STRING,
    key_uncertainty      STRING,
    trigger_type         STRING,           -- AI_AGENT | RE_EVALUATION | HUMAN
    status               STRING,           -- PENDING | MERGED | REJECTED
    company_id           STRING,           -- QB company that owns the source record
    record_type          STRING,           -- vendor | customer
    reviewer             STRING,
    reviewed_at          TIMESTAMP(3),
    created_at           TIMESTAMP(3),
    PRIMARY KEY (match_id) NOT ENFORCED
) WITH (
    'merge-engine'               = 'deduplicate',
    'bucket'                     = '4',
    'tag.automatic-creation'     = 'watermark',
    'tag.num-retained-max'       = '365',
    'snapshot.time-retained'     = '168h',
    'snapshot.num-retained'      = '200'
);

-- ── Connection Alerts ────────────────────────────────────────
-- Connection lifecycle alerts (UI notifications).
-- Replaces MySQL connection_alerts table.

CREATE TABLE IF NOT EXISTS connection_alerts (
    alert_id             STRING,
    connection_id        STRING,
    user_id              STRING,
    alert_type           STRING,           -- connection_added | entity_created | entity_merged | merge_review
    title                STRING,
    message              STRING,
    entity_name          STRING,
    target_entity_id     STRING,
    confidence           DECIMAL(4, 3),
    dismissed            BOOLEAN,
    created_at           TIMESTAMP(3),
    PRIMARY KEY (alert_id) NOT ENFORCED
) WITH (
    'merge-engine'               = 'deduplicate',
    'bucket'                     = '4',
    'tag.automatic-creation'     = 'watermark',
    'tag.num-retained-max'       = '365',
    'snapshot.time-retained'     = '168h',
    'snapshot.num-retained'      = '200'
);

-- ── Resolution Audit ───────────────────────────────────────
-- Append-only log of every entity resolution decision.
-- No updates — each audit entry is immutable once written.

CREATE TABLE IF NOT EXISTS resolution_audit (
    audit_id             STRING,
    event_id             STRING,
    record_id            STRING,
    perspective          STRING,
    decision             STRING,         -- MERGE | NEW_ENTITY | REVIEW | NO_MERGE_FOUND
    trigger_type         STRING,         -- AI_AGENT | RE_EVALUATION | HUMAN
    target_golden_id     STRING,
    absorbed_golden_id   STRING,
    confidence           DECIMAL(4, 3),
    dimension_scores     STRING,         -- JSON object
    reasoning            STRING,
    key_factors          STRING,         -- JSON array
    candidates_evaluated INT,
    llm_calls            INT,
    embedding_calls      INT,
    total_duration_ms    INT,
    evaluation_chain     STRING,         -- JSON array
    golden_record_before STRING,         -- JSON object (snapshot)
    golden_record_after  STRING,         -- JSON object (snapshot)
    created_at           TIMESTAMP(3),
    PRIMARY KEY (audit_id) NOT ENFORCED
) WITH (
    'merge-engine'               = 'deduplicate',
    'bucket'                     = '4',
    'tag.automatic-creation'     = 'watermark',
    'tag.num-retained-max'       = '365',
    'snapshot.time-retained'     = '168h',
    'snapshot.num-retained'      = '200'
);
