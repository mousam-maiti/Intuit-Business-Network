-- Auto-generated self-contained CDC job
-- Source: quickbooks.match_decisions → Paimon: network_graph.match_decisions

CREATE CATALOG paimon WITH (
    'type' = 'paimon',
    'warehouse' = 'file:///Users/mousammaiti/IntuitQB-StreamHouse'
);

USE CATALOG default_catalog;
USE default_database;


CREATE TEMPORARY TABLE mysql_match_decisions (
    decision_id  BIGINT,
    match_id     STRING,
    decided_by   BIGINT,
    resolution   STRING,
    source_entity_id STRING,
    candidate_entity_id STRING,
    confidence_at_decision DECIMAL(4, 3),
    decided_at   TIMESTAMP(3),
    PRIMARY KEY (decision_id) NOT ENFORCED
) WITH (
    'connector'     = 'mysql-cdc',
    'hostname'      = 'localhost',
    'port'          = '3306',
    'username'      = 'cdc_reader',
    'password'      = 'cdc_reader_pass',
    'database-name' = 'quickbooks',
    'table-name'    = 'match_decisions',
    'server-id'     = '5408'
);

SET 'execution.runtime-mode' = 'streaming';
SET 'execution.checkpointing.interval' = '30s';

INSERT INTO paimon.network_graph.match_decisions
SELECT * FROM default_catalog.default_database.mysql_match_decisions;
