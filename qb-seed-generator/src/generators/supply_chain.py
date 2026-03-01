"""Inter-company supply chain connections.

Defines which QB companies are vendors/customers of each other,
enabling multi-hop supply chain paths through the entity graph.

When the entity resolution pipeline processes these records, it matches
them to existing QB_USER golden records via EIN/name/location, creating
QB_USER-to-QB_USER edges that enable multi-hop traversal.

Topology (20 edges):
  Tier 1: Property Mgmt (9) hires GCs and trades
  Tier 2: GCs (1,2,3,4) hire specialty subs
  Tier 3: RedLine Interiors (8) hires Landscaping (10)

Longest chains: 9->1->8->10->PHANTOM (4 hops),
                9->2->5->PHANTOM (3 hops)
"""

import random
from src.generators.companies import QB_ACCOUNTS
from src.generators.variations import generate_variation

# ── (buyer_company_id, seller_company_id) ──
# buyer pays seller = seller is a vendor in buyer's books
INTER_COMPANY_EDGES = [
    # Tier 1: Travis County PM (9) hires GCs + trades
    (9, 1),   # PM hires Acme Construction
    (9, 2),   # PM hires BuildRight GC
    (9, 5),   # PM hires Capital City Plumbing
    (9, 6),   # PM hires ATX Electrical
    (9, 10),  # PM hires Bluebonnet Landscaping

    # Tier 2a: Acme Construction (1) hires subs
    (1, 5),   # Acme hires Capital City Plumbing
    (1, 6),   # Acme hires ATX Electrical
    (1, 7),   # Acme hires Precision HVAC
    (1, 8),   # Acme hires RedLine Interiors

    # Tier 2b: BuildRight GC (2) hires subs
    (2, 5),   # BuildRight hires Capital City Plumbing
    (2, 6),   # BuildRight hires ATX Electrical
    (2, 7),   # BuildRight hires Precision HVAC
    (2, 10),  # BuildRight hires Bluebonnet Landscaping

    # Tier 2c: Hill Country Homes (3) hires subs
    (3, 5),   # Hill Country hires Capital City Plumbing
    (3, 7),   # Hill Country hires Precision HVAC
    (3, 8),   # Hill Country hires RedLine Interiors

    # Tier 2d: Lone Star Renovations (4) hires subs
    (4, 6),   # Lone Star hires ATX Electrical
    (4, 7),   # Lone Star hires Precision HVAC
    (4, 8),   # Lone Star hires RedLine Interiors

    # Tier 3: RedLine Interiors (8) hires landscaping for staging
    (8, 10),  # RedLine hires Bluebonnet Landscaping
]

# Category mapping for bill line item generation
IC_CATEGORY_MAP = {
    1: "Contractor",       # Acme Construction
    2: "Contractor",       # BuildRight GC
    3: "Contractor",       # Hill Country Homes
    4: "Contractor",       # Lone Star Renovations
    5: "Plumbing",         # Capital City Plumbing
    6: "Electrical",       # ATX Electrical
    7: "HVAC",             # Precision HVAC
    8: "Contractor",       # RedLine Interiors (interior finishing)
    9: "Contractor",       # Travis County PM
    10: "Contractor",      # Bluebonnet Landscaping
}

# Map company_id -> QB_ACCOUNTS entry for quick lookup
_COMPANY_BY_ID = {c["company_id"]: c for c in QB_ACCOUNTS}


def build_intercompany_pool_entries():
    """Create pseudo-pool entries from QB company data.

    These look like regular vendor pool entries so the rest of the pipeline
    (assignments, transactions) can handle them uniformly. Each seller
    company becomes one pool entry with serial_id "IC-{company_id:03d}".

    Returns:
        list of pool-entry dicts keyed by serial_id
    """
    seller_ids = sorted({seller for _, seller in INTER_COMPANY_EDGES})
    entries = []

    for sid in seller_ids:
        company = _COMPANY_BY_ID[sid]
        serial_id = f"IC-{sid:03d}"

        entry = {
            "serial_id": serial_id,
            "canonical_name": company["company_name"],
            "ein": company["ein"],  # always present for IC entries
            "contact_name": company["primary_contact"],
            "email": company["email"],
            "phone": company["phone"],
            "category": IC_CATEGORY_MAP.get(sid, "Contractor"),
            "naics": None,
            "commodities": [],
            "street_address": company["street_address"],
            "city": company["city"],
            "state": company["state"],
            "zip": company["zip"],
            "website": company.get("website"),
            "expected_annual_volume": None,
            "payment_terms": random.choice(["net_30", "net_15"]),
            "legal_structure": company.get("legal_structure", "LLC"),
            "avg_transaction_size": 5000,
            "hub_likelihood": "high",
            "is_intercompany": True,
            "source_company_id": sid,
        }
        entries.append(entry)

    return entries


def get_intercompany_assignments():
    """Return mapping of IC serial_id -> list of buyer company_ids.

    Returns:
        dict: {"IC-005": [1, 2, 3], "IC-006": [1, 2, 4], ...}
    """
    assignments = {}
    for buyer_id, seller_id in INTER_COMPANY_EDGES:
        serial_id = f"IC-{seller_id:03d}"
        assignments.setdefault(serial_id, []).append(buyer_id)
    return assignments


def get_buyer_ic_count():
    """Return how many IC vendors each buyer company has.

    Returns:
        dict: {company_id: count} e.g. {9: 5, 1: 4, 2: 4, ...}
    """
    counts = {}
    for buyer_id, _ in INTER_COMPANY_EDGES:
        counts[buyer_id] = counts.get(buyer_id, 0) + 1
    return counts
