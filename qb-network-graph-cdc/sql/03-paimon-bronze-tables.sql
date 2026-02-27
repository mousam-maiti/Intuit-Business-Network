-- ============================================================
-- Step 3: Paimon Bronze Target Tables
-- ============================================================

USE CATALOG paimon;
USE network_graph;

CREATE TABLE IF NOT EXISTS staged_companies (
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
    'changelog-producer' = 'input',
    'merge-engine'       = 'deduplicate',
    'bucket'             = '4',
    'snapshot.time-retained' = '72h',
    'snapshot.num-retained'  = '100'
);

CREATE TABLE IF NOT EXISTS staged_vendors (
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
    'changelog-producer' = 'input',
    'merge-engine'       = 'deduplicate',
    'bucket'             = '4',
    'snapshot.time-retained' = '72h',
    'snapshot.num-retained'  = '100'
);

CREATE TABLE IF NOT EXISTS staged_customers (
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
    'changelog-producer' = 'input',
    'merge-engine'       = 'deduplicate',
    'bucket'             = '4',
    'snapshot.time-retained' = '72h',
    'snapshot.num-retained'  = '100'
);

CREATE TABLE IF NOT EXISTS staged_bills (
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
    'changelog-producer' = 'input',
    'merge-engine'       = 'deduplicate',
    'bucket'             = '8',
    'snapshot.time-retained' = '72h',
    'snapshot.num-retained'  = '100'
);

CREATE TABLE IF NOT EXISTS staged_bill_line_items (
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
    'changelog-producer' = 'input',
    'merge-engine'       = 'deduplicate',
    'bucket'             = '8',
    'snapshot.time-retained' = '72h',
    'snapshot.num-retained'  = '100'
);

CREATE TABLE IF NOT EXISTS staged_invoices (
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
    'changelog-producer' = 'input',
    'merge-engine'       = 'deduplicate',
    'bucket'             = '8',
    'snapshot.time-retained' = '72h',
    'snapshot.num-retained'  = '100'
);

CREATE TABLE IF NOT EXISTS staged_invoice_line_items (
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
    'changelog-producer' = 'input',
    'merge-engine'       = 'deduplicate',
    'bucket'             = '8',
    'snapshot.time-retained' = '72h',
    'snapshot.num-retained'  = '100'
);

CREATE TABLE IF NOT EXISTS staged_payments (
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
    'changelog-producer' = 'input',
    'merge-engine'       = 'deduplicate',
    'bucket'             = '8',
    'snapshot.time-retained' = '72h',
    'snapshot.num-retained'  = '100'
);

CREATE TABLE IF NOT EXISTS match_decisions (
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
    'changelog-producer' = 'input',
    'merge-engine'       = 'deduplicate',
    'bucket'             = '4',
    'snapshot.time-retained' = '72h',
    'snapshot.num-retained'  = '100'
);
