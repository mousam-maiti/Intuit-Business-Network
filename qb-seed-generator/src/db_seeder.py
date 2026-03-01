"""Load generated seed data directly into MySQL."""

from src.config import cfg


def _connect():
    try:
        import mysql.connector
    except ImportError:
        raise ImportError(
            "mysql-connector-python is required for DB seeding.\n"
            "Install it: pip install mysql-connector-python"
        )
    return mysql.connector.connect(
        host=cfg.MYSQL_HOST,
        port=cfg.MYSQL_PORT,
        database=cfg.MYSQL_DATABASE,
        user=cfg.MYSQL_USER,
        password=cfg.MYSQL_PASSWORD,
    )


def _truncate_all(cursor):
    """Truncate all tables in dependency order."""
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    tables = [
        "payments", "bill_line_items", "invoice_line_items",
        "bills", "invoices", "products_services",
        "vendors", "customers", "companies",
    ]
    for t in tables:
        cursor.execute(f"TRUNCATE TABLE {t}")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    print("  Truncated all tables")


def _insert_companies(cursor, companies):
    sql = """
        INSERT INTO companies
        (company_id, company_name, legal_name, legal_structure, ein,
         industry_category, street_address, city, state, zip,
         primary_contact, email, phone, website, status)
        VALUES
        (%(company_id)s, %(company_name)s, %(legal_name)s, %(legal_structure)s, %(ein)s,
         %(industry_category)s, %(street_address)s, %(city)s, %(state)s, %(zip)s,
         %(primary_contact)s, %(email)s, %(phone)s, %(website)s, 'active')
    """
    cursor.executemany(sql, companies)
    print(f"  Inserted {cursor.rowcount} companies")


def _insert_vendors(cursor, vendor_records):
    sql = """
        INSERT INTO vendors
        (vendor_id, company_id, display_name, ein, contact_name, email, phone,
         category, commodity, street_address, city, state, zip,
         website, expected_volume, payment_terms, is_active)
        VALUES
        (%(vendor_id)s, %(company_id)s, %(display_name)s, %(ein)s,
         %(contact_name)s, %(email)s, %(phone)s,
         %(category)s, %(commodity)s, %(street_address)s, %(city)s, %(state)s, %(zip)s,
         %(website)s, %(expected_volume)s, %(payment_terms)s, %(is_active)s)
    """
    cursor.executemany(sql, vendor_records)
    print(f"  Inserted {cursor.rowcount} vendors")


def _insert_customers(cursor, customer_records):
    sql = """
        INSERT INTO customers
        (customer_id, company_id, display_name, ein, contact_name, email, phone,
         category, commodity, street_address, city, state, zip,
         website, expected_volume, payment_terms, is_active)
        VALUES
        (%(customer_id)s, %(company_id)s, %(display_name)s, %(ein)s,
         %(contact_name)s, %(email)s, %(phone)s,
         %(category)s, %(commodity)s, %(street_address)s, %(city)s, %(state)s, %(zip)s,
         %(website)s, %(expected_volume)s, %(payment_terms)s, %(is_active)s)
    """
    cursor.executemany(sql, customer_records)
    print(f"  Inserted {cursor.rowcount} customers")


def _insert_bills(cursor, bills):
    sql = """
        INSERT INTO bills
        (bill_id, company_id, vendor_id, bill_number, bill_date, due_date,
         subtotal, tax, total, balance_due, status, memo)
        VALUES
        (%(bill_id)s, %(company_id)s, %(vendor_id)s, %(bill_number)s,
         %(bill_date)s, %(due_date)s, %(subtotal)s, %(tax)s, %(total)s,
         %(balance_due)s, %(status)s, %(memo)s)
    """
    # Batch insert in chunks to avoid packet size issues
    chunk = 5000
    total = 0
    for i in range(0, len(bills), chunk):
        cursor.executemany(sql, bills[i:i + chunk])
        total += cursor.rowcount
    print(f"  Inserted {total} bills")


def _insert_bill_line_items(cursor, items):
    sql = """
        INSERT INTO bill_line_items
        (line_item_id, bill_id, item_id, description, quantity,
         unit_price, amount, expense_category)
        VALUES
        (%(line_item_id)s, %(bill_id)s, %(item_id)s, %(description)s,
         %(quantity)s, %(unit_price)s, %(amount)s, %(expense_category)s)
    """
    chunk = 5000
    total = 0
    for i in range(0, len(items), chunk):
        cursor.executemany(sql, items[i:i + chunk])
        total += cursor.rowcount
    print(f"  Inserted {total} bill line items")


def _insert_invoices(cursor, invoices):
    sql = """
        INSERT INTO invoices
        (invoice_id, company_id, customer_id, invoice_number, invoice_date, due_date,
         subtotal, tax, total, balance_due, status, memo)
        VALUES
        (%(invoice_id)s, %(company_id)s, %(customer_id)s, %(invoice_number)s,
         %(invoice_date)s, %(due_date)s, %(subtotal)s, %(tax)s, %(total)s,
         %(balance_due)s, %(status)s, %(memo)s)
    """
    chunk = 5000
    total = 0
    for i in range(0, len(invoices), chunk):
        cursor.executemany(sql, invoices[i:i + chunk])
        total += cursor.rowcount
    print(f"  Inserted {total} invoices")


def _insert_invoice_line_items(cursor, items):
    sql = """
        INSERT INTO invoice_line_items
        (line_item_id, invoice_id, item_id, description, quantity,
         unit_price, amount, service_category)
        VALUES
        (%(line_item_id)s, %(invoice_id)s, %(item_id)s, %(description)s,
         %(quantity)s, %(unit_price)s, %(amount)s, %(service_category)s)
    """
    chunk = 5000
    total = 0
    for i in range(0, len(items), chunk):
        cursor.executemany(sql, items[i:i + chunk])
        total += cursor.rowcount
    print(f"  Inserted {total} invoice line items")


def _insert_payments(cursor, payments):
    sql = """
        INSERT INTO payments
        (payment_id, company_id, payment_type, invoice_id, bill_id,
         amount, payment_date, payment_method, reference_number, memo)
        VALUES
        (%(payment_id)s, %(company_id)s, %(payment_type)s, %(invoice_id)s, %(bill_id)s,
         %(amount)s, %(payment_date)s, %(payment_method)s, %(reference_number)s, %(memo)s)
    """
    chunk = 5000
    total = 0
    for i in range(0, len(payments), chunk):
        cursor.executemany(sql, payments[i:i + chunk])
        total += cursor.rowcount
    print(f"  Inserted {total} payments")


def seed_mysql(
    companies, vendor_records, customer_records,
    bills, bill_line_items, invoices, invoice_line_items, payments,
):
    """Load all generated data into MySQL."""
    print(f"\nConnecting to MySQL at {cfg.MYSQL_HOST}:{cfg.MYSQL_PORT}/{cfg.MYSQL_DATABASE}...")
    conn = _connect()
    cursor = conn.cursor()

    try:
        print("Seeding MySQL:")
        _truncate_all(cursor)
        _insert_companies(cursor, companies)
        _insert_vendors(cursor, vendor_records)
        _insert_customers(cursor, customer_records)
        _insert_bills(cursor, bills)
        _insert_bill_line_items(cursor, bill_line_items)
        _insert_invoices(cursor, invoices)
        _insert_invoice_line_items(cursor, invoice_line_items)
        _insert_payments(cursor, payments)
        conn.commit()
        print("\n\u2713 MySQL seeded successfully")
    except Exception as e:
        conn.rollback()
        print(f"\n\u2717 MySQL seeding failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()
