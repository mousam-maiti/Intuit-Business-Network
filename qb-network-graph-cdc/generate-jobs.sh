#!/bin/bash
# Generates 9 self-contained CDC job SQL files in sql/jobs/
# Each file includes: catalog + source table + paimon target + INSERT

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JOBS_DIR="$SCRIPT_DIR/sql/jobs"
mkdir -p "$JOBS_DIR"

CATALOG_PREAMBLE='CREATE CATALOG paimon WITH (
    '"'"'type'"'"' = '"'"'paimon'"'"',
    '"'"'warehouse'"'"' = '"'"'file:///Users/mousammaiti/IntuitQB-StreamHouse'"'"'
);'

# Helper: write a complete job file
write_job() {
    local filename="$1"
    local source_ddl="$2"
    local source_table="$3"
    local target_table="$4"

    cat > "$JOBS_DIR/$filename" << ENDOFSQL
-- Auto-generated self-contained CDC job
-- Source: quickbooks.${source_table#mysql_} → Paimon: network_graph.${target_table}

${CATALOG_PREAMBLE}

USE CATALOG default_catalog;
USE default_database;

${source_ddl}

SET 'execution.runtime-mode' = 'streaming';
SET 'execution.checkpointing.interval' = '30s';

INSERT INTO paimon.network_graph.${target_table}
SELECT * FROM default_catalog.default_database.${source_table};
ENDOFSQL
    echo "  ✓ $filename"
}

echo "Generating CDC job files..."

# 1. Companies
write_job "01-companies.sql" "
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
);" "mysql_companies" "staged_companies"

# 2. Vendors
write_job "02-vendors.sql" "
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
);" "mysql_vendors" "staged_vendors"

# 3. Customers
write_job "03-customers.sql" "
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
);" "mysql_customers" "staged_customers"

# 4. Bills
write_job "04-bills.sql" "
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
);" "mysql_bills" "staged_bills"

# 5. Bill Line Items
write_job "05-bill-line-items.sql" "
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
);" "mysql_bill_line_items" "staged_bill_line_items"

# 6. Invoices
write_job "06-invoices.sql" "
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
);" "mysql_invoices" "staged_invoices"

# 7. Invoice Line Items
write_job "07-invoice-line-items.sql" "
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
);" "mysql_invoice_line_items" "staged_invoice_line_items"

# 8. Payments
write_job "08-payments.sql" "
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
);" "mysql_payments" "staged_payments"

# 9. Match Decisions
write_job "09-match-decisions.sql" "
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
);" "mysql_match_decisions" "match_decisions"

echo ""
echo "Done. 9 job files in $JOBS_DIR/"
