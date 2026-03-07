-- ============================================================
-- Step 1: Create Paimon Catalog
-- ============================================================

CREATE CATALOG paimon WITH (
    'type' = 'paimon',
    'warehouse' = 'file:///Users/mousammaiti/IntuitQB-StreamHouse'
);

USE CATALOG paimon;

CREATE DATABASE IF NOT EXISTS network_graph;

USE network_graph;
