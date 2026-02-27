-- Auto-generated self-contained CDC job
-- Source: quickbooks.payments → Paimon: network_graph.staged_payments

CREATE CATALOG paimon WITH (
    'type' = 'paimon',
    'warehouse' = 'file:///Users/mousammaiti/IntuitQB-StreamHouse'
);

USE CATALOG default_catalog;
USE default_database;


CREATE TEMPORARY TABLE mysql_payments (
    payment_id   BIGINT,
    company_id   BIGINT,
    payment_type STRING,
    invoice_id   BIGINT,
    bill_id      BIGINT,
    amount       DECIMAL(12, 2),
    payment_date DATE,
    payment_method STRING,
    reference_number STRING,
    memo         STRING,
    created_at   TIMESTAMP(3),
    updated_at   TIMESTAMP(3),
    PRIMARY KEY (payment_id) NOT ENFORCED
) WITH (
    'connector'     = 'mysql-cdc',
    'hostname'      = 'localhost',
    'port'          = '3306',
    'username'      = 'cdc_reader',
    'password'      = 'cdc_reader_pass',
    'database-name' = 'quickbooks',
    'table-name'    = 'payments',
    'server-id'     = '5407'
);

SET 'execution.runtime-mode' = 'streaming';
SET 'execution.checkpointing.interval' = '30s';

INSERT INTO paimon.network_graph.staged_payments
SELECT * FROM default_catalog.default_database.mysql_payments;
