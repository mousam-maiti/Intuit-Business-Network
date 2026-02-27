"""Assign ground truth pool entries to the 10 QB accounts.

For each QB account, selects which vendors/clients they reference,
generates display name variations, and applies per-account field sparsity.

This is what creates the entity resolution challenge:
  - V-042 "Bob's Plumbing LLC" appears in Acme's books as "Bobs Plumbing"
  - V-042 appears in BuildRight's books as "Bob's Plumbing L.L.C."
  - V-042 appears in Hill Country's books as "BP Plumbing"
"""

import random
from src.config import cfg
from src.generators.variations import generate_variation


_HUB_PRIORITY = {"high": 0, "medium": 1, "low": 2}


def _decide_accounts_for_entry(entry, all_company_ids):
    """Decide which QB accounts reference this pool entry, based on hub_likelihood."""
    hub = entry["hub_likelihood"]
    if hub == "high":
        n = random.randint(cfg.HUB_HIGH_MIN, min(cfg.HUB_HIGH_MAX, len(all_company_ids)))
    elif hub == "medium":
        n = random.randint(cfg.HUB_MEDIUM_MIN, min(cfg.HUB_MEDIUM_MAX, len(all_company_ids)))
    else:
        n = random.randint(cfg.HUB_LOW_MIN, min(cfg.HUB_LOW_MAX, len(all_company_ids)))
    return random.sample(all_company_ids, n)


def _trim_to_target(account_map, pool, cid, excess):
    """Remove *cid* from *excess* entries, dropping low-hub entries first."""
    assigned = [
        entry for entry in pool
        if cid in account_map[entry["serial_id"]]
    ]
    # Sort so low-hub entries come first (trimmed preferentially)
    assigned.sort(key=lambda e: -_HUB_PRIORITY[e["hub_likelihood"]])
    for entry in assigned:
        if excess <= 0:
            break
        account_map[entry["serial_id"]].remove(cid)
        excess -= 1


def _pad_to_target(account_map, pool, cid, deficit):
    """Add *cid* to *deficit* unassigned entries, adding low-hub entries first."""
    candidates = [
        entry for entry in pool
        if cid not in account_map[entry["serial_id"]]
    ]
    # Sort so low-hub entries come first (padded preferentially)
    candidates.sort(key=lambda e: -_HUB_PRIORITY[e["hub_likelihood"]])
    for entry in candidates:
        if deficit <= 0:
            break
        account_map[entry["serial_id"]].append(cid)
        deficit -= 1


def _apply_sparsity(entry, field, fill_rate):
    """Probabilistically include or exclude a field value."""
    ground_truth = entry.get(field)
    if ground_truth is None:
        return None  # Pool already had it empty
    if random.random() < fill_rate:
        return ground_truth
    return None


def _build_record(pool_entry, company_id, is_vendor):
    """Build a vendor/customer MySQL record for a specific QB account.

    Applies name variation and per-account field sparsity.
    """
    canonical = pool_entry["canonical_name"]
    city = pool_entry["city"]

    # Decide display name: use canonical or a variation
    if random.random() < cfg.NAME_VARIATION_PROB:
        display_name = generate_variation(canonical, city)
    else:
        display_name = canonical

    fill = cfg.FILL_RATES
    commodities = pool_entry.get("commodities", [])

    record = {
        "company_id": company_id,
        "pool_serial_id": pool_entry["serial_id"],     # tracking only — not in MySQL

        # Identity (form section 1)
        "display_name": display_name,
        "ein": _apply_sparsity(pool_entry, "ein", fill["ein"]),
        "contact_name": _apply_sparsity(pool_entry, "contact_name", fill["contact_name"]),
        "email": _apply_sparsity(pool_entry, "email", fill["email"]),
        "phone": _apply_sparsity(pool_entry, "phone", fill["phone"]),

        # Industry (form section 2)
        "category": _apply_sparsity(pool_entry, "category", fill["category"]),
        "commodity": (
            "; ".join(random.sample(commodities, min(len(commodities), random.randint(1, 2))))
            if commodities and random.random() < fill["commodity"]
            else None
        ),

        # Location (form section 3)
        "street_address": _apply_sparsity(pool_entry, "street_address", fill["street_address"]),
        "city": pool_entry["city"],      # city almost always present
        "state": pool_entry["state"],
        "zip": _apply_sparsity(pool_entry, "zip", fill["street_address"]),  # ZIP follows address

        # Behavioral (form section 4)
        "website": _apply_sparsity(pool_entry, "website", fill["website"]),
        "expected_volume": _apply_sparsity(pool_entry, "expected_annual_volume", fill["expected_volume"]),
        "payment_terms": _apply_sparsity(pool_entry, "payment_terms", fill["payment_terms"]),

        # Metadata
        "is_active": True,
    }

    return record


def generate_assignments(vendor_pool, client_pool, company_ids):
    """Generate vendor and customer records for all QB accounts.

    Returns:
        vendor_records: list of dicts (one per vendor-per-account assignment)
        customer_records: list of dicts (one per customer-per-account assignment)
        assignment_map: dict mapping serial_id → list of company_ids (for tracking)
    """
    vendor_records = []
    customer_records = []
    assignment_map = {"vendors": {}, "clients": {}}

    vendor_id_counter = 1
    customer_id_counter = 1

    targets = cfg.COMPANY_TARGETS  # {cid: (vendors, customers)} or None

    # ── Assign vendors ──
    # First pass: hub-based initial assignment
    vendor_account_map = {}  # serial_id → [company_ids]
    for v in vendor_pool:
        accounts = _decide_accounts_for_entry(v, company_ids)
        vendor_account_map[v["serial_id"]] = accounts

    # Second pass: enforce exact targets or ensure minimums
    if targets:
        for cid in company_ids:
            vendor_target = targets[cid][0]
            current = sum(1 for accts in vendor_account_map.values() if cid in accts)
            if current > vendor_target:
                _trim_to_target(vendor_account_map, vendor_pool, cid, current - vendor_target)
            elif current < vendor_target:
                _pad_to_target(vendor_account_map, vendor_pool, cid, vendor_target - current)
    else:
        # Backwards compatible: ensure minimums via padding
        for cid in company_ids:
            current = sum(1 for accts in vendor_account_map.values() if cid in accts)
            needed = cfg.VENDORS_PER_ACCOUNT_MIN
            if current < needed:
                candidates = [
                    v for v in vendor_pool
                    if cid not in vendor_account_map[v["serial_id"]]
                ]
                random.shuffle(candidates)
                for v in candidates[:needed - current]:
                    vendor_account_map[v["serial_id"]].append(cid)

    # Second pass: generate records
    for v in vendor_pool:
        accounts = vendor_account_map[v["serial_id"]]
        assignment_map["vendors"][v["serial_id"]] = accounts
        for cid in accounts:
            rec = _build_record(v, cid, is_vendor=True)
            rec["vendor_id"] = vendor_id_counter
            vendor_id_counter += 1
            vendor_records.append(rec)

    # ── Assign clients ──
    client_account_map = {}
    for c in client_pool:
        accounts = _decide_accounts_for_entry(c, company_ids)
        client_account_map[c["serial_id"]] = accounts

    # Enforce exact targets or ensure minimums
    if targets:
        for cid in company_ids:
            client_target = targets[cid][1]
            current = sum(1 for accts in client_account_map.values() if cid in accts)
            if current > client_target:
                _trim_to_target(client_account_map, client_pool, cid, current - client_target)
            elif current < client_target:
                _pad_to_target(client_account_map, client_pool, cid, client_target - current)
    else:
        for cid in company_ids:
            current = sum(1 for accts in client_account_map.values() if cid in accts)
            needed = cfg.CLIENTS_PER_ACCOUNT_MIN
            if current < needed:
                candidates = [
                    c for c in client_pool
                    if cid not in client_account_map[c["serial_id"]]
                ]
                random.shuffle(candidates)
                for c in candidates[:needed - current]:
                    client_account_map[c["serial_id"]].append(cid)

    for c in client_pool:
        accounts = client_account_map[c["serial_id"]]
        assignment_map["clients"][c["serial_id"]] = accounts
        for cid in accounts:
            rec = _build_record(c, cid, is_vendor=False)
            rec["customer_id"] = customer_id_counter
            customer_id_counter += 1
            customer_records.append(rec)

    return vendor_records, customer_records, assignment_map
