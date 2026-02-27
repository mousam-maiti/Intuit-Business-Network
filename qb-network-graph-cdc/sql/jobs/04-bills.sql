-- Auto-generated self-contained CDC job
-- Source: quickbooks.bills → Paimon: network_graph.staged_bills

CREATE CATALOG paimon WITH (
    'type' = 'paimon',
    'warehouse' = 'file:///Users/mousammaiti/IntuitQB-StreamHouse'
);

USE CATALOG default_catalog;
USE default_database;


CREATE TEMPORARY TABLE mysql_bills (
    bill_id      BIGINT,
    company_id   BIGINT,
    vendor_id    BIGINT,
    bill_number  STRING,
    bill_date    DATE,
    due_date     DATE,
    subtotal     DECIMAL(12, 2),
    tax          DECIMAL(12, 2),
    total        DECIMAL(12, 2),
    balance_due  DECIMAL(12, 2),
    status       STRING,
    memo         STRING,
    created_at   TIMESTAMP(3),
    updated_at   TIMESTAMP(3),
    PRIMARY KEY (bill_id) NOT ENFORCED
) WITH (
    'connector'     = 'mysql-cdc',
    'hostname'      = 'localhost',
    'port'          = '3306',
    'username'      = 'cdc_reader',
    'password'      = 'cdc_reader_pass',
    'database-name' = 'quickbooks',
    'table-name'    = 'bills',
    'server-id'     = '5403'
);

SET 'execution.runtime-mode' = 'streaming';
SET 'execution.checkpointing.interval' = '30s';

INSERT INTO paimon.network_graph.staged_bills
SELECT * FROM default_catalog.default_database.mysql_bills;
