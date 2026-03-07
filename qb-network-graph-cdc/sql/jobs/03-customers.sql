-- Auto-generated self-contained CDC job
-- Source: quickbooks.customers → Paimon: network_graph.staged_customers

CREATE CATALOG paimon WITH (
    'type' = 'paimon',
    'warehouse' = 'file:///Users/mousammaiti/IntuitQB-StreamHouse'
);

USE CATALOG default_catalog;
USE default_database;


CREATE TEMPORARY TABLE mysql_customers (
    customer_id  BIGINT,
    company_id   BIGINT,
    display_name STRING,
    ein          STRING,
    contact_name STRING,
    email        STRING,
    phone        STRING,
    category     STRING,
    commodity    STRING,
    street_address STRING,
    city         STRING,
    state        STRING,
    zip          STRING,
    website      STRING,
    expected_volume DECIMAL(14, 2),
    payment_terms STRING,
    is_active    BOOLEAN,
    created_at   TIMESTAMP(3),
    updated_at   TIMESTAMP(3),
    PRIMARY KEY (customer_id) NOT ENFORCED
) WITH (
    'connector'     = 'mysql-cdc',
    'hostname'      = 'localhost',
    'port'          = '3306',
    'username'      = 'cdc_reader',
    'password'      = 'cdc_reader_pass',
    'database-name' = 'quickbooks',
    'table-name'    = 'customers',
    'server-id'     = '5402'
);

SET 'execution.runtime-mode' = 'streaming';
SET 'execution.checkpointing.interval' = '30s';

INSERT INTO paimon.network_graph.staged_customers
SELECT * FROM default_catalog.default_database.mysql_customers;
