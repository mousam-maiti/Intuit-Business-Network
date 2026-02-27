-- ============================================================
-- Step 2: CDC Source Tables (MySQL binlog → Flink)
-- ============================================================

USE CATALOG default_catalog;
USE default_database;

-- ── Companies ──
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

-- ── Vendors ──
CREATE TEMPORARY TABLE mysql_vendors (
    vendor_id    BIGINT,
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
    PRIMARY KEY (vendor_id) NOT ENFORCED
) WITH (
    'connector'     = 'mysql-cdc',
    'hostname'      = 'localhost',
    'port'          = '3306',
    'username'      = 'cdc_reader',
    'password'      = 'cdc_reader_pass',
    'database-name' = 'quickbooks',
    'table-name'    = 'vendors',
    'server-id'     = '5401'
);

-- ── Customers ──
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

-- ── Bills ──
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

-- ── Bill Line Items ──
CREATE TEMPORARY TABLE mysql_bill_line_items (
    line_item_id BIGINT,
    bill_id      BIGINT,
    item_id      BIGINT,
    description  STRING,
    quantity     DECIMAL(10, 2),
    unit_price   DECIMAL(12, 2),
    amount       DECIMAL(12, 2),
    expense_category STRING,
    PRIMARY KEY (line_item_id) NOT ENFORCED
) WITH (
    'connector'     = 'mysql-cdc',
    'hostname'      = 'localhost',
    'port'          = '3306',
    'username'      = 'cdc_reader',
    'password'      = 'cdc_reader_pass',
    'database-name' = 'quickbooks',
    'table-name'    = 'bill_line_items',
    'server-id'     = '5404'
);

-- ── Invoices ──
CREATE TEMPORARY TABLE mysql_invoices (
    invoice_id   BIGINT,
    company_id   BIGINT,
    customer_id  BIGINT,
    invoice_number STRING,
    invoice_date DATE,
    due_date     DATE,
    subtotal     DECIMAL(12, 2),
    tax          DECIMAL(12, 2),
    total        DECIMAL(12, 2),
    balance_due  DECIMAL(12, 2),
    status       STRING,
    memo         STRING,
    created_at   TIMESTAMP(3),
    updated_at   TIMESTAMP(3),
    PRIMARY KEY (invoice_id) NOT ENFORCED
) WITH (
    'connector'     = 'mysql-cdc',
    'hostname'      = 'localhost',
    'port'          = '3306',
    'username'      = 'cdc_reader',
    'password'      = 'cdc_reader_pass',
    'database-name' = 'quickbooks',
    'table-name'    = 'invoices',
    'server-id'     = '5405'
);

-- ── Invoice Line Items ──
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

-- ── Payments ──
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

-- ── Match Decisions (feedback loop) ──
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
