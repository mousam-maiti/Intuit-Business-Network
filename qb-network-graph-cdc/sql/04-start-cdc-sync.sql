-- ============================================================
-- Step 4: Start CDC Sync Jobs
-- ============================================================
-- NOTE: run-pipeline.sh (option 4) submits these individually.
-- This file is for manual use in the SQL client.
-- Paste each INSERT one at a time, wait for Job ID.
-- ============================================================

SET 'execution.runtime-mode' = 'streaming';
SET 'execution.checkpointing.interval' = '30s';

INSERT INTO paimon.network_graph.staged_companies
SELECT * FROM default_catalog.default_database.mysql_companies;

INSERT INTO paimon.network_graph.staged_vendors
SELECT * FROM default_catalog.default_database.mysql_vendors;

INSERT INTO paimon.network_graph.staged_customers
SELECT * FROM default_catalog.default_database.mysql_customers;

INSERT INTO paimon.network_graph.staged_bills
SELECT * FROM default_catalog.default_database.mysql_bills;

INSERT INTO paimon.network_graph.staged_bill_line_items
SELECT * FROM default_catalog.default_database.mysql_bill_line_items;

INSERT INTO paimon.network_graph.staged_invoices
SELECT * FROM default_catalog.default_database.mysql_invoices;

INSERT INTO paimon.network_graph.staged_invoice_line_items
SELECT * FROM default_catalog.default_database.mysql_invoice_line_items;

INSERT INTO paimon.network_graph.staged_payments
SELECT * FROM default_catalog.default_database.mysql_payments;

INSERT INTO paimon.network_graph.match_decisions
SELECT * FROM default_catalog.default_database.mysql_match_decisions;
