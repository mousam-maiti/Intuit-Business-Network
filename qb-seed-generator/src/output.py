"""Write generated data to seed/ directory as JSON and CSV."""

import json
import csv
from pathlib import Path
from src.config import cfg


def _ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def _write_json(data, filepath):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  → {filepath} ({len(data)} records)")


def _write_csv(data, filepath, headers=None):
    if not data:
        return
    if headers is None:
        headers = list(data[0].keys())
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in data:
            writer.writerow({k: (v if v is not None else "") for k, v in row.items()})
    print(f"  → {filepath} ({len(data)} records)")


def write_all(
    vendor_pool, client_pool,
    companies,
    vendor_records, customer_records, assignment_map,
    bills, bill_line_items, invoices, invoice_line_items, payments,
):
    """Write everything to seed/ directory."""
    base = cfg.SEED_DIR
    _ensure_dir(base / "pools")
    _ensure_dir(base / "assignments")
    _ensure_dir(base / "mysql")

    # ── Pools (ground truth) ──
    print("\nPools (ground truth):")
    _write_json(vendor_pool, base / "pools" / "vendor_pool.json")
    _write_json(client_pool, base / "pools" / "client_pool.json")
    _write_csv(vendor_pool, base / "pools" / "vendor_pool.csv")
    _write_csv(client_pool, base / "pools" / "client_pool.csv")

    # ── Companies ──
    print("\nCompanies:")
    _write_json(companies, base / "mysql" / "companies.json")

    # ── Assignments (what each account sees) ──
    print("\nAssignments:")
    _write_json(vendor_records, base / "assignments" / "vendor_assignments.json")
    _write_json(customer_records, base / "assignments" / "customer_assignments.json")
    _write_json(assignment_map, base / "assignments" / "assignment_map.json")
    _write_csv(vendor_records, base / "assignments" / "vendor_assignments.csv")
    _write_csv(customer_records, base / "assignments" / "customer_assignments.csv")

    # ── MySQL-ready records ──
    print("\nMySQL records:")
    _write_json(bills, base / "mysql" / "bills.json")
    _write_json(bill_line_items, base / "mysql" / "bill_line_items.json")
    _write_json(invoices, base / "mysql" / "invoices.json")
    _write_json(invoice_line_items, base / "mysql" / "invoice_line_items.json")
    _write_json(payments, base / "mysql" / "payments.json")

    # ── Supply chain edges (debug) ──
    from src.generators.supply_chain import INTER_COMPANY_EDGES
    from src.generators.companies import QB_ACCOUNTS
    _company_names = {c["company_id"]: c["company_name"] for c in QB_ACCOUNTS}
    sc_edges = [
        {
            "buyer_id": b, "seller_id": s,
            "buyer_name": _company_names.get(b, f"Company {b}"),
            "seller_name": _company_names.get(s, f"Company {s}"),
        }
        for b, s in INTER_COMPANY_EDGES
    ]
    _ensure_dir(base / "debug")
    _write_json(sc_edges, base / "debug" / "supply_chain_edges.json")

    # ── Summary stats ──
    ic_vendor_count = sum(1 for r in vendor_records if r.get("is_intercompany"))
    pool_vendor_count = len(vendor_records) - ic_vendor_count

    print("\n" + "=" * 60)
    print("SEED DATA SUMMARY")
    print("=" * 60)
    print(f"  Companies:            {len(companies):>8,}")
    print(f"  Vendor pool (truth):  {len(vendor_pool):>8,}")
    print(f"  Client pool (truth):  {len(client_pool):>8,}")
    print(f"  Vendor records:       {len(vendor_records):>8,}  (across all accounts)")
    print(f"    Inter-company:      {ic_vendor_count:>8,}  ({len(INTER_COMPANY_EDGES)} edges)")
    print(f"    Pool vendors:       {pool_vendor_count:>8,}")
    print(f"  Customer records:     {len(customer_records):>8,}  (across all accounts)")
    print(f"  Bills:                {len(bills):>8,}")
    print(f"  Bill line items:      {len(bill_line_items):>8,}")
    print(f"  Invoices:             {len(invoices):>8,}")
    print(f"  Invoice line items:   {len(invoice_line_items):>8,}")
    print(f"  Payments:             {len(payments):>8,}")
    print()

    # Per-account breakdown
    print("Per-account breakdown:")
    for cid in sorted(set(r["company_id"] for r in vendor_records)):
        v_total = sum(1 for r in vendor_records if r["company_id"] == cid)
        v_ic = sum(1 for r in vendor_records if r["company_id"] == cid and r.get("is_intercompany"))
        c_count = sum(1 for r in customer_records if r["company_id"] == cid)
        b_count = sum(1 for b in bills if b["company_id"] == cid)
        i_count = sum(1 for i in invoices if i["company_id"] == cid)
        ic_label = f" ({v_ic} IC)" if v_ic else ""
        print(f"  Company {cid:>2d}: {v_total:>3d} vendors{ic_label}, {c_count:>3d} customers, "
              f"{b_count:>5d} bills, {i_count:>5d} invoices")

    # Name variation stats
    canonical_to_variants = {}
    for rec in vendor_records:
        serial = rec["pool_serial_id"]
        name = rec["display_name"]
        canonical_to_variants.setdefault(serial, set()).add(name)

    multi_name = {k: v for k, v in canonical_to_variants.items() if len(v) > 1}
    print(f"\n  Vendors with multiple display names: {len(multi_name)}/{len(canonical_to_variants)}")
    for serial, names in list(multi_name.items())[:5]:
        print(f"    {serial}: {names}")
