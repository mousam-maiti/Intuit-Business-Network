#!/usr/bin/env python3
"""
QB Network Graph — Seed Data Generator

Two independent steps:
  1. Generate seed files:   python -m src.main generate
  2. Load into MySQL:       python -m src.main seed

Generate always writes to seed/. Seed always reads from seed/.
This makes it repeatable — same files, same DB state every time.

Combined:                   python -m src.main generate seed
"""

import sys
import random
import argparse

from src.config import cfg


def cmd_generate():
    """Generate all seed data → seed/ directory."""
    from src.generators.companies import QB_ACCOUNTS
    from src.generators.pools import generate_vendor_pool, generate_client_pool
    from src.generators.assignments import generate_assignments
    from src.generators.transactions import generate_transactions
    from src.output import write_all

    random.seed(cfg.RANDOM_SEED)

    print("=" * 60)
    print("QB Network Graph — Seed Data Generator")
    print("=" * 60)
    print(f"  Random seed:    {cfg.RANDOM_SEED}")
    print(f"  Vendor pool:    {cfg.VENDOR_POOL_SIZE}")
    print(f"  Client pool:    {cfg.CLIENT_POOL_SIZE}")
    print(f"  QB accounts:    {cfg.QB_ACCOUNT_COUNT}")
    print(f"  Name variation: {cfg.NAME_VARIATION_PROB:.0%}")
    print(f"  Transactions:   {cfg.TXN_START} → {cfg.TXN_END}")
    print(f"  Output:         {cfg.SEED_DIR}")
    print()

    # Step 1: Ground truth pools
    print("Step 1: Generating ground truth pools...")
    vendor_pool = generate_vendor_pool()
    client_pool = generate_client_pool()
    print(f"  {len(vendor_pool)} vendors, {len(client_pool)} clients")

    # Step 2: QB accounts
    companies = QB_ACCOUNTS[:cfg.QB_ACCOUNT_COUNT]
    company_ids = [c["company_id"] for c in companies]
    print(f"\nStep 2: Using {len(companies)} QB accounts")

    # Step 3: Assign pools to accounts with variations
    print("\nStep 3: Assigning pools to accounts...")
    vendor_records, customer_records, assignment_map = generate_assignments(
        vendor_pool, client_pool, company_ids
    )
    print(f"  {len(vendor_records)} vendor records, {len(customer_records)} customer records")

    # Step 4: Generate transactions
    print("\nStep 4: Generating transactions...")
    vendor_pool_map = {v["serial_id"]: v for v in vendor_pool}
    bills, bill_li, invoices, invoice_li, payments = generate_transactions(
        vendor_records, customer_records, vendor_pool_map
    )
    print(f"  {len(bills)} bills, {len(invoices)} invoices, {len(payments)} payments")

    # Step 5: Write to seed/
    print("\nStep 5: Writing seed files...")
    write_all(
        vendor_pool, client_pool,
        companies,
        vendor_records, customer_records, assignment_map,
        bills, bill_li, invoices, invoice_li, payments,
    )


def cmd_seed():
    """Read seed/ files → load into MySQL. Repeatable."""
    import json
    from src.db_seeder import seed_mysql

    base = cfg.SEED_DIR

    required_files = [
        base / "mysql" / "companies.json",
        base / "assignments" / "vendor_assignments.json",
        base / "assignments" / "customer_assignments.json",
        base / "mysql" / "bills.json",
        base / "mysql" / "bill_line_items.json",
        base / "mysql" / "invoices.json",
        base / "mysql" / "invoice_line_items.json",
        base / "mysql" / "payments.json",
    ]

    missing = [f for f in required_files if not f.exists()]
    if missing:
        print("ERROR: Seed files not found. Run 'generate' first.")
        for f in missing:
            print(f"  Missing: {f}")
        sys.exit(1)

    print(f"Reading seed files from {base}...")
    companies = json.loads((base / "mysql" / "companies.json").read_text())
    vendor_records = json.loads((base / "assignments" / "vendor_assignments.json").read_text())
    customer_records = json.loads((base / "assignments" / "customer_assignments.json").read_text())
    bills = json.loads((base / "mysql" / "bills.json").read_text())
    bill_li = json.loads((base / "mysql" / "bill_line_items.json").read_text())
    invoices = json.loads((base / "mysql" / "invoices.json").read_text())
    invoice_li = json.loads((base / "mysql" / "invoice_line_items.json").read_text())
    payments = json.loads((base / "mysql" / "payments.json").read_text())

    print(f"  Companies:       {len(companies):>8,}")
    print(f"  Vendors:         {len(vendor_records):>8,}")
    print(f"  Customers:       {len(customer_records):>8,}")
    print(f"  Bills:           {len(bills):>8,}")
    print(f"  Bill line items: {len(bill_li):>8,}")
    print(f"  Invoices:        {len(invoices):>8,}")
    print(f"  Inv line items:  {len(invoice_li):>8,}")
    print(f"  Payments:        {len(payments):>8,}")

    seed_mysql(
        companies, vendor_records, customer_records,
        bills, bill_li, invoices, invoice_li, payments,
    )


def main():
    parser = argparse.ArgumentParser(
        description="QB Network Graph Seed Generator",
        epilog="Examples:\n"
               "  python -m src.main generate         # Generate seed files\n"
               "  python -m src.main seed             # Load seed files into MySQL\n"
               "  python -m src.main generate seed    # Both\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "commands",
        nargs="+",
        choices=["generate", "seed"],
        help="generate = create seed files, seed = load into MySQL",
    )
    args = parser.parse_args()

    for cmd in args.commands:
        if cmd == "generate":
            cmd_generate()
        elif cmd == "seed":
            cmd_seed()

    print("\nDone.")


if __name__ == "__main__":
    main()
