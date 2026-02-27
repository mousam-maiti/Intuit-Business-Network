-- ============================================================
-- Verify Entity Connections (run queries individually)
-- ============================================================

CREATE CATALOG paimon WITH (
    'type' = 'paimon',
    'warehouse' = '${WAREHOUSE_PATH}'
);
USE CATALOG paimon;
USE network_graph;
SET 'execution.runtime-mode' = 'batch';


-- 1. Counts by type
SELECT connection_type, COUNT(*) AS cnt
FROM entity_connections
GROUP BY connection_type;


-- 2. Acme's vendors
SELECT display_name, city, state, category, total_volume, transaction_count
FROM entity_connections
WHERE company_id = 1 AND connection_type = 'vendor'
ORDER BY total_volume DESC LIMIT 10;


-- 3. Hub candidates
SELECT display_name, city, state, COUNT(*) AS accounts, SUM(total_volume) AS volume
FROM entity_connections
WHERE connection_type = 'vendor'
GROUP BY display_name, city, state
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC LIMIT 10;
