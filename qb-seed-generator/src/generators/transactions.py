"""Generate transactions: bills (company→vendor), invoices (company→customer), and payments.

Bills represent what the company pays vendors.
Invoices represent what customers pay the company.
Payments confirm money moved.
"""

import random
from datetime import timedelta
from src.config import cfg

# Line item templates by category
BILL_LINE_ITEMS_BY_CATEGORY = {
    "Lumber": [
        ("2x4 framing lumber — 100 board ft", "Materials", 150, 600),
        ("3/4 inch plywood sheets x10", "Materials", 300, 800),
        ("OSB sheathing 4x8", "Materials", 200, 500),
        ("Pressure treated deck boards", "Materials", 400, 1200),
    ],
    "Concrete": [
        ("Ready-mix concrete 5 yards", "Materials", 500, 2000),
        ("Rebar #4 bundle", "Materials", 100, 400),
        ("Concrete blocks 8-inch x100", "Materials", 150, 500),
    ],
    "Plumbing": [
        ("PVC pipe 3/4 inch — 200ft", "Materials", 100, 400),
        ("Copper fittings assorted", "Materials", 80, 300),
        ("Water heater 50gal", "Materials", 400, 1200),
        ("Plumbing fixture set", "Materials", 200, 800),
    ],
    "Electrical": [
        ("Romex wire 12/2 — 250ft", "Materials", 60, 200),
        ("Breaker panel 200A", "Materials", 200, 600),
        ("LED recessed lighting x12", "Materials", 100, 400),
    ],
    "HVAC": [
        ("AC condenser unit 3-ton", "Materials", 1500, 4000),
        ("Ductwork — flex 6 inch 25ft", "Materials", 50, 200),
        ("Thermostat — programmable", "Materials", 50, 200),
    ],
    "Contractor": [
        ("Labor — plumbing rough-in", "Subcontractor", 1500, 5000),
        ("Labor — electrical wiring", "Subcontractor", 1200, 4000),
        ("Labor — HVAC installation", "Subcontractor", 2000, 6000),
        ("Labor — drywall hanging", "Subcontractor", 800, 3000),
        ("Labor — painting interior", "Subcontractor", 600, 2500),
    ],
    "Rental": [
        ("Excavator rental — 1 week", "Equipment", 800, 3000),
        ("Scaffolding rental — 2 weeks", "Equipment", 200, 800),
        ("Generator rental — daily", "Equipment", 50, 200),
    ],
    "Insurance": [
        ("General liability premium — quarterly", "Insurance", 500, 3000),
        ("Workers comp premium — quarterly", "Insurance", 800, 4000),
    ],
    "default": [
        ("Professional services", "Services", 500, 5000),
        ("Consulting fee", "Services", 200, 2000),
        ("Materials and supplies", "Materials", 100, 1500),
    ],
}

INVOICE_LINE_ITEMS = [
    ("Kitchen remodel — demolition", "Labor", 2000, 8000),
    ("Kitchen remodel — cabinets and install", "Labor + Materials", 5000, 20000),
    ("Bathroom renovation — tile and fixtures", "Labor + Materials", 3000, 12000),
    ("Room addition — framing", "Labor", 4000, 15000),
    ("Electrical rough-in", "Labor", 1200, 4000),
    ("Plumbing rough-in and finish", "Labor", 1500, 5000),
    ("HVAC installation", "Labor + Materials", 3000, 10000),
    ("Interior painting — 4 rooms", "Labor + Materials", 800, 3000),
    ("Drywall — hang and finish", "Labor + Materials", 1000, 4000),
    ("Flooring — hardwood install 500sqft", "Labor + Materials", 2000, 8000),
    ("Exterior siding repair", "Labor + Materials", 1500, 5000),
    ("Roof repair — 10 squares", "Labor + Materials", 3000, 10000),
    ("Foundation inspection and repair", "Labor", 500, 3000),
    ("Permit fees", "Administrative", 200, 1000),
    ("Project management fee", "Administrative", 500, 3000),
    ("Custom millwork — built-in shelving", "Labor + Materials", 2000, 8000),
    ("Landscape — sod install 2000sqft", "Labor + Materials", 1000, 4000),
    ("Concrete driveway pour", "Labor + Materials", 2000, 8000),
    ("Fence installation — cedar 150ft", "Labor + Materials", 3000, 10000),
    ("Deck construction — composite 200sqft", "Labor + Materials", 4000, 15000),
]


def _random_date():
    """Random date in the configured transaction window."""
    delta = (cfg.TXN_END - cfg.TXN_START).days
    return cfg.TXN_START + timedelta(days=random.randint(0, delta))


def _pick_line_items(category, count, is_bill=True):
    """Pick realistic line items based on vendor/category."""
    if is_bill:
        templates = BILL_LINE_ITEMS_BY_CATEGORY.get("default", [])
        for key, items in BILL_LINE_ITEMS_BY_CATEGORY.items():
            if key.lower() in (category or "").lower():
                templates = items
                break
    else:
        templates = INVOICE_LINE_ITEMS

    items = []
    for _ in range(count):
        tpl = random.choice(templates)
        desc, cat, lo, hi = tpl
        unit_price = round(random.uniform(lo, hi), 2)
        qty = random.choice([1, 1, 1, 2, 3, 5]) if is_bill else 1
        items.append({
            "description": desc,
            "quantity": qty,
            "unit_price": unit_price,
            "amount": round(qty * unit_price, 2),
            "category": cat,
        })
    return items


def generate_transactions(vendor_records, customer_records, vendor_pool_map):
    """Generate bills, invoices, payments, and line items.

    Args:
        vendor_records: list of assigned vendor records (with vendor_id, company_id)
        customer_records: list of assigned customer records (with customer_id, company_id)
        vendor_pool_map: dict serial_id → pool entry (for category lookup)

    Returns:
        bills, bill_line_items, invoices, invoice_line_items, payments
    """
    bills = []
    bill_line_items_all = []
    invoices = []
    invoice_line_items_all = []
    payments = []

    bill_id = 1
    bill_li_id = 1
    invoice_id = 1
    invoice_li_id = 1
    payment_id = 1

    # ── Bills (company pays vendor) ──
    for vrec in vendor_records:
        pool_serial = vrec["pool_serial_id"]
        pool_entry = vendor_pool_map.get(pool_serial, {})
        category = pool_entry.get("category", "")
        avg_txn = pool_entry.get("avg_transaction_size", 1000)

        n_txn = random.randint(cfg.TXN_PER_REL_MIN, cfg.TXN_PER_REL_MAX)

        for _ in range(n_txn):
            bill_date = _random_date()
            n_lines = random.choices([1, 2, 3, 4], weights=[40, 30, 20, 10])[0]
            lines = _pick_line_items(category, n_lines, is_bill=True)

            subtotal = round(sum(li["amount"] for li in lines), 2)
            tax = round(subtotal * 0.0825, 2) if random.random() < 0.6 else 0
            total = round(subtotal + tax, 2)
            is_paid = random.random() < 0.85

            bill = {
                "bill_id": bill_id,
                "company_id": vrec["company_id"],
                "vendor_id": vrec["vendor_id"],
                "bill_number": f"B-{bill_id:06d}",
                "bill_date": bill_date.isoformat(),
                "due_date": (bill_date + timedelta(days=random.choice([0, 15, 30, 60]))).isoformat(),
                "subtotal": subtotal,
                "tax": tax,
                "total": total,
                "balance_due": 0 if is_paid else total,
                "status": "paid" if is_paid else random.choice(["open", "partial", "overdue"]),
                "memo": None,
            }
            bills.append(bill)

            for li in lines:
                bill_line_items_all.append({
                    "line_item_id": bill_li_id,
                    "bill_id": bill_id,
                    "item_id": None,
                    "description": li["description"],
                    "quantity": li["quantity"],
                    "unit_price": li["unit_price"],
                    "amount": li["amount"],
                    "expense_category": li["category"],
                })
                bill_li_id += 1

            # Payment for paid bills
            if is_paid:
                pay_date = bill_date + timedelta(days=random.randint(1, 45))
                if pay_date > cfg.TXN_END:
                    pay_date = cfg.TXN_END
                payments.append({
                    "payment_id": payment_id,
                    "company_id": vrec["company_id"],
                    "payment_type": "bill_payment",
                    "invoice_id": None,
                    "bill_id": bill_id,
                    "amount": total,
                    "payment_date": pay_date.isoformat(),
                    "payment_method": random.choice(["check", "ach", "credit_card", "ach", "check"]),
                    "reference_number": f"PMT-{payment_id:06d}",
                    "memo": None,
                })
                payment_id += 1

            bill_id += 1

    # ── Invoices (customer pays company) ──
    for crec in customer_records:
        n_txn = random.randint(cfg.TXN_PER_REL_MIN, max(cfg.TXN_PER_REL_MIN, cfg.TXN_PER_REL_MAX // 2))

        for _ in range(n_txn):
            inv_date = _random_date()
            n_lines = random.choices([1, 2, 3, 5], weights=[20, 35, 30, 15])[0]
            lines = _pick_line_items(None, n_lines, is_bill=False)

            subtotal = round(sum(li["amount"] for li in lines), 2)
            tax = round(subtotal * 0.0825, 2) if random.random() < 0.5 else 0
            total = round(subtotal + tax, 2)
            is_paid = random.random() < 0.80

            inv = {
                "invoice_id": invoice_id,
                "company_id": crec["company_id"],
                "customer_id": crec["customer_id"],
                "invoice_number": f"INV-{invoice_id:06d}",
                "invoice_date": inv_date.isoformat(),
                "due_date": (inv_date + timedelta(days=random.choice([0, 15, 30]))).isoformat(),
                "subtotal": subtotal,
                "tax": tax,
                "total": total,
                "balance_due": 0 if is_paid else total,
                "status": "paid" if is_paid else random.choice(["sent", "partial", "overdue"]),
                "memo": None,
            }
            invoices.append(inv)

            for li in lines:
                invoice_line_items_all.append({
                    "line_item_id": invoice_li_id,
                    "invoice_id": invoice_id,
                    "item_id": None,
                    "description": li["description"],
                    "quantity": li["quantity"],
                    "unit_price": li["unit_price"],
                    "amount": li["amount"],
                    "service_category": li["category"],
                })
                invoice_li_id += 1

            if is_paid:
                pay_date = inv_date + timedelta(days=random.randint(1, 60))
                if pay_date > cfg.TXN_END:
                    pay_date = cfg.TXN_END
                payments.append({
                    "payment_id": payment_id,
                    "company_id": crec["company_id"],
                    "payment_type": "invoice_payment",
                    "invoice_id": invoice_id,
                    "bill_id": None,
                    "amount": total,
                    "payment_date": pay_date.isoformat(),
                    "payment_method": random.choice(["check", "ach", "credit_card", "ach"]),
                    "reference_number": f"PMT-{payment_id:06d}",
                    "memo": None,
                })
                payment_id += 1

            invoice_id += 1

    return bills, bill_line_items_all, invoices, invoice_line_items_all, payments
