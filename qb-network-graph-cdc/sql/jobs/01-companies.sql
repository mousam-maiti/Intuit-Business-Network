-- Auto-generated self-contained CDC job
-- Source: quickbooks.companies → Paimon: network_graph.staged_companies

CREATE CATALOG paimon WITH (
    'type' = 'paimon',
    'warehouse' = 'file:///Users/mousammaiti/IntuitQB-StreamHouse'
);

USE CATALOG default_catalog;
USE default_database;


CREATE TEMPORARY TABLE mysql_companies (
    company_id   BIGINT,
    company_name STRING,
    legal_name   STRING,
    legal_structure STRING,
    ein          STRING,
    industry_category STRING,
    street_address STRING,
    city         STRING,
    state        STRING,
    zip          STRING,
    primary_contact STRING,
    email        STRING,
    phone        STRING,
    website      STRING,
    status       STRING,
    created_at   TIMESTAMP(3),
    updated_at   TIMESTAMP(3),
    PRIMARY KEY (company_id) NOT ENFORCED
) WITH (
    'connector'     = 'mysql-cdc',
    'hostname'      = 'localhost',
    'port'          = '3306',
    'username'      = 'cdc_reader',
    'password'      = 'cdc_reader_pass',
    'database-name' = 'quickbooks',
    'table-name'    = 'companies',
    'server-id'     = '5400'
);

SET 'execution.runtime-mode' = 'streaming';
SET 'execution.checkpointing.interval' = '30s';

INSERT INTO paimon.network_graph.staged_companies
SELECT * FROM default_catalog.default_database.mysql_companies;
