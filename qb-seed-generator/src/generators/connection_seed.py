"""Seed 2: Direct connections for Acme Construction (company_id=1).

Two categories of connections POST'd via the backend API:
  1. Network matches  — businesses that ALREADY exist in the Intuit Business
     Network (Seed 1) but with varied names/sparse fields.  The entity agent
     should find a fuzzy match and park them as pending_resolution.
  2. Brand-new entities — businesses NOT in the network at all.  The entity
     agent creates new golden records.

Usage:  python -m src.main connections
"""

import json
import time
import random
import requests

from src.config import cfg

BACKEND_URL = "http://localhost:8087/api/v1"

# ── Network overlap connections ──────────────────────────────────────────
# These mirror Seed 1 businesses but with name variations, missing fields,
# and slightly different details so entity resolution has to work for it.
#
# Format: (varied_name, connType, category, commodity, city, state, zip,
#           ein_if_known, email_if_known, phone_if_known, contact_if_known)

NETWORK_OVERLAP = [
    # CloudPeak Solutions (G-5fab9c83) — EIN 741603789
    ("CloudPeak Solutions Inc", "vendor", "Software", "cloud hosting; SaaS",
     "Austin", "TX", "78758", "74-1603789", "sales@cloudpeak.com", None, None),

    # Pecan Partners CPA (G-dd3c20ea) — EIN 754898004
    ("Pecan Partners CPA LLC", "vendor", "Accounting", "tax preparation; bookkeeping",
     "Austin", "TX", "78701", "75-4898004", None, "(512) 555-0190", "David Chen"),

    # Clearpath Insurance (G-b61e2bef) — no EIN in Neo4j, rely on name + location
    ("Clearpath Insurance", "vendor", "Insurance", "commercial insurance; workers comp",
     "Dallas", "TX", "75201", None, "info@clearpathins.com", None, None),

    # Capitol Law Group (G-6d86cdb6) — EIN 749117385
    ("Capitol Law Group LLC", "vendor", "Legal Services", "contracts; business formation",
     "Austin", "TX", "78701", "74-9117385", "reception@capitollaw.com", None, None),

    # NetWave Communications (G-87899cb4) — no EIN in Neo4j, rely on name + location
    ("NetWave Communications LLC", "vendor", "Telecom", "fiber internet; VoIP",
     "Austin", "TX", "78702", None, None, "(512) 443-8800", None),

    # Amplify Marketing Co (G-71a4ec07) — EIN 742961536
    ("Amplify Marketing LLC", "vendor", "Marketing", "brand strategy; content marketing",
     "Austin", "TX", "78704", "74-2961536", "hello@amplifymarketing.com", None, None),

    # Southside Office Supply (G-06f5520d) — EIN 759417048, email_domain southsideoff.com
    ("Southside Office Supplies", "vendor", "Office Supplies", "paper; ink cartridges; furniture",
     "Austin", "TX", "78745", "75-9417048", "orders@southsideoff.com", None, "Mike Torres"),

    # SafeGuard Fire & Safety (G-783521d7) — EIN 478718484, email_domain safeguardfir.com
    ("SafeGuard Fire Safety", "vendor", "Safety", "fire extinguishers; first aid kits; hard hats",
     "Austin", "TX", "78753", "47-8718484", None, "(512) 299-4100", None),

    # Monarch Moving Co (G-16999113) — EIN 467296398
    ("Monarch Moving LLC", "vendor", "Moving", "commercial moving; packing",
     "Austin", "TX", "78741", "46-7296398", "dispatch@monarchmoving.com", None, None),

    # SunBelt Roofing & Solar (G-a8bff6ad) — EIN 849508296, email_domain sunbeltroofi.com
    ("SunBelt Roofing and Solar", "vendor", "Roofing", "roof install; solar panels",
     "Austin", "TX", "78748", "84-9508296", None, "(512) 600-3300", "James Hardy"),

    # Capitol Janitorial Supply (G-768eaeb8) — EIN 744334671, email_domain capitoljanit.com
    ("Capitol Janitorial Supplies", "vendor", "Cleaning", "disinfectant; mops; trash bags",
     "Austin", "TX", "78756", "74-4334671", None, None, None),

    # Greenfield Land Development (G-01725b8c) — EIN 474890935
    ("Greenfield Land Dev", "client", "Land Development", "lot clearing; site grading",
     "Georgetown", "TX", "78626", "47-4890935", "office@greenfielddev.com", None, "Robert Fields"),
]


# ── Brand-new connections (not in network) ───────────────────────────────
# These are completely new businesses that will create fresh golden records.

NEW_CONNECTIONS = [
    ("Garcia Brothers Excavation", "vendor", "Excavation",
     "site excavation; trenching; grading",
     "Kyle", "TX", "78640",
     "83-4921577", "tony@garciaexcavation.com", "(512) 301-4455", "Tony Garcia"),

    ("Precision Glass & Mirror", "vendor", "Glass & Glazing",
     "commercial glass; storefront; mirrors",
     "Round Rock", "TX", "78664",
     None, "sales@precisionglass.com", "(512) 218-9000", None),

    ("Central Texas Welding", "vendor", "Welding",
     "structural welding; fabrication; railing",
     "San Marcos", "TX", "78666",
     "74-8832156", None, "(512) 878-2200", "Frank Weaver"),

    ("Bridgewater Engineering", "vendor", "Civil Engineering",
     "structural engineering; foundation design",
     "Austin", "TX", "78703",
     "82-1567443", "info@bridgewatereng.com", None, "Sarah Lin"),

    ("RiverBend Security Systems", "vendor", "Security",
     "alarm systems; CCTV; access control",
     "Austin", "TX", "78745",
     None, "install@riverbendsecurity.com", "(512) 444-7700", None),

    ("Texas Star Elevator Co", "vendor", "Elevator",
     "elevator install; maintenance; inspection",
     "Houston", "TX", "77002",
     "76-3398821", None, "(713) 550-1234", "Oscar Mendez"),

    ("Hilltop Fire Protection", "vendor", "Fire Protection",
     "sprinkler systems; fire alarm; backflow",
     "Cedar Park", "TX", "78613",
     None, "service@hilltopfire.com", None, "Beth Kowalski"),

    ("South Austin Fence Co", "vendor", "Fencing",
     "chain link; wood fence; iron gate",
     "Austin", "TX", "78748",
     "84-2910334", "quote@southaustinfence.com", "(512) 707-3000", None),

    ("Magnolia Creek Homes", "client", "Home Builder",
     "custom homes; new construction",
     "Dripping Springs", "TX", "78620",
     "75-8824109", "contact@magnoliacreekhomes.com", "(512) 394-8500", "Lisa Park"),

    ("Eastside Community Church", "client", "Church",
     "fellowship hall; sanctuary renovation",
     "Austin", "TX", "78702",
     None, "admin@eastsidechurch.org", "(512) 478-2100", "Pastor James Wright"),

    ("Lockhart ISD Facilities", "client", "School District",
     "school renovation; gym expansion; portables",
     "Kyle", "TX", "78640",
     "74-6001287", "facilities@lockhartisd.net", "(512) 398-0000", "Diana Ruiz"),

    ("Mueller Development Group", "client", "Property Developer",
     "mixed-use development; urban infill",
     "Austin", "TX", "78723",
     "82-5543298", "projects@muellerdev.com", "(512) 926-8800", "Brad Thompson"),

    ("Westover Hills HOA", "client", "HOA",
     "community center; pool maintenance; fencing",
     "Austin", "TX", "78749",
     None, "board@westoverhillshoa.com", None, "Karen Mitchell"),
]


def cmd_connections():
    """Seed direct connections for Acme Construction via backend API."""
    random.seed(cfg.RANDOM_SEED + 3000)

    all_connections = []

    # Network overlap connections
    for (name, conn_type, category, commodity,
         city, state, zip_code, ein, email, phone, contact) in NETWORK_OVERLAP:
        all_connections.append({
            "name": name,
            "connType": conn_type,
            "category": category,
            "commodity": commodity,
            "city": city,
            "state": state,
            "zip": zip_code,
            "ein": ein,
            "email": email,
            "phone": phone,
            "contactName": contact,
            "source": "network_overlap",
        })

    # Brand-new connections
    for (name, conn_type, category, commodity,
         city, state, zip_code, ein, email, phone, contact) in NEW_CONNECTIONS:
        all_connections.append({
            "name": name,
            "connType": conn_type,
            "category": category,
            "commodity": commodity,
            "city": city,
            "state": state,
            "zip": zip_code,
            "ein": ein,
            "email": email,
            "phone": phone,
            "contactName": contact,
            "source": "new",
        })

    print("=" * 60)
    print("QB Network Graph — Direct Connection Seed")
    print("=" * 60)
    print(f"\n  Network overlap: {len(NETWORK_OVERLAP)} (should match existing golden records)")
    print(f"  Brand-new:       {len(NEW_CONNECTIONS)} (should create new golden records)")
    print(f"  Total:           {len(all_connections)}")

    # Write manifest
    manifest_dir = cfg.SEED_DIR / "connections"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "connections.json").write_text(
        json.dumps(all_connections, indent=2, default=str)
    )
    print(f"  Manifest:        {manifest_dir}/connections.json")

    # POST each connection via the backend API
    print(f"\n  Posting connections to {BACKEND_URL}/connections ...")
    session = requests.Session()
    session.headers["Content-Type"] = "application/json"

    ok, fail = 0, 0
    for conn in all_connections:
        payload = {k: v for k, v in conn.items() if k != "source" and v is not None}
        try:
            r = session.post(f"{BACKEND_URL}/connections", json=payload, timeout=15)
            if r.status_code == 200:
                data = r.json().get("data", {})
                tag = "OVERLAP" if conn["source"] == "network_overlap" else "NEW"
                print(f"    [{tag}] {conn['name']}: id={data.get('id')}")
                ok += 1
            else:
                fail += 1
                print(f"    FAIL {conn['name']}: {r.status_code} {r.text[:100]}")
        except Exception as e:
            fail += 1
            print(f"    ERROR {conn['name']}: {e}")

        # Small delay to avoid overwhelming the classifier stream
        time.sleep(0.3)

    print(f"\n  Summary: {ok}/{len(all_connections)} posted ({fail} failed)")
    if ok > 0:
        print(f"\n  The classifier orchestrator will now pick these up from")
        print(f"  Paimon entity_connections and run entity resolution.")
        print(f"  Check /tmp/qb-classifier.log for progress.")
