-- Auto-generated self-contained CDC job
-- Source: quickbooks.invoice_line_items → Paimon: network_graph.staged_invoice_line_items

CREATE CATALOG paimon WITH (
    'type' = 'paimon',
    'warehouse' = 'file:///Users/mousammaiti/IntuitQB-StreamHouse'
);

USE CATALOG default_catalog;
USE default_database;


CREATE TEMPORARY TABLE mysql_invoice_line_items (
    line_item_id BIGINT,
    invoice_id   BIGINT,
    item_id      BIGINT,
    description  STRING,
    quantity     DECIMAL(10, 2),
    unit_price   DECIMAL(12, 2),
    amount       DECIMAL(12, 2),
    service_category STRING,
    PRIMARY KEY (line_item_id) NOT ENFORCED
) WITH (
    'connector'     = 'mysql-cdc',
    'hostname'      = 'localhost',
    'port'          = '3306',
    'username'      = 'cdc_reader',
    'password'      = 'cdc_reader_pass',
    'database-name' = 'quickbooks',
    'table-name'    = 'invoice_line_items',
    'server-id'     = '5406'
);

SET 'execution.runtime-mode' = 'streaming';
SET 'execution.checkpointing.interval' = '30s';

INSERT INTO paimon.network_graph.staged_invoice_line_items
SELECT * FROM default_catalog.default_database.mysql_invoice_line_items;
