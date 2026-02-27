-- ============================================================
-- Verify CDC Sync
-- ============================================================

USE CATALOG paimon;
USE network_graph;
SET 'execution.runtime-mode' = 'batch';

-- Row counts
SELECT 'staged_companies' AS tbl, COUNT(*) AS cnt FROM staged_companies
UNION ALL SELECT 'staged_vendors', COUNT(*) FROM staged_vendors
UNION ALL SELECT 'staged_customers', COUNT(*) FROM staged_customers
UNION ALL SELECT 'staged_bills', COUNT(*) FROM staged_bills
UNION ALL SELECT 'staged_bill_line_items', COUNT(*) FROM staged_bill_line_items
UNION ALL SELECT 'staged_invoices', COUNT(*) FROM staged_invoices
UNION ALL SELECT 'staged_invoice_line_items', COUNT(*) FROM staged_invoice_line_items
UNION ALL SELECT 'staged_payments', COUNT(*) FROM staged_payments;

-- Spot check: Acme's vendors
SELECT vendor_id, display_name, category, city
FROM staged_vendors
WHERE company_id = 1
LIMIT 10;

-- Name variations for lumber vendors across accounts
SELECT company_id, display_name, ein, city
FROM staged_vendors
WHERE display_name LIKE '%Lumber%' OR display_name LIKE '%lumber%'
ORDER BY display_name
LIMIT 20;
