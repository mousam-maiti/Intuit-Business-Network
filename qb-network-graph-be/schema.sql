-- QB Network Graph Backend — New tables for native perspective + connections
-- Run: mysql -u qb_admin -p quickbooks < schema.sql

-- 1. native_overrides: JSON blob per (user_id, entity_id)
CREATE TABLE IF NOT EXISTS native_overrides (
    user_id VARCHAR(64) NOT NULL DEFAULT '1',
    entity_id VARCHAR(64) NOT NULL,
    overrides JSON NOT NULL,
    created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (user_id, entity_id)
);

-- 2. native_merges: user-driven entity merge records
CREATE TABLE IF NOT EXISTS native_merges (
    merge_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL DEFAULT '1',
    source_entity_id VARCHAR(64) NOT NULL,
    target_entity_id VARCHAR(64) NOT NULL,
    origin VARCHAR(16) NOT NULL DEFAULT 'user',
    reason TEXT,
    migrated_relationships JSON,
    created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_nm_user (user_id)
);

-- 3. manual_connections: user-added vendor/client links
CREATE TABLE IF NOT EXISTS manual_connections (
    connection_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL DEFAULT '1',
    conn_type VARCHAR(16) NOT NULL,
    entity_id VARCHAR(64),
    entity_snapshot JSON,
    added_via VARCHAR(128),
    confidence FLOAT,
    created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_mc_user (user_id)
);

-- 4. auto_connections: CDC pipeline resolved connections
CREATE TABLE IF NOT EXISTS auto_connections (
    connection_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL DEFAULT '1',
    conn_type VARCHAR(16) NOT NULL,
    source_doc VARCHAR(128),
    source_date VARCHAR(32),
    entity_id VARCHAR(64) NOT NULL,
    resolution_type VARCHAR(16) DEFAULT 'auto',
    tier INT DEFAULT 1,
    confidence FLOAT,
    latency_ms INT,
    created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_ac_user (user_id)
);
