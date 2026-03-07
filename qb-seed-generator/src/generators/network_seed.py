"""Seed 1: Intuit Business Network — 100 global businesses with relationships.

Generates golden records and inter-business relationships across diverse
industry clusters, then POSTs them to the MCP sync API (port 8084) which
writes to Neo4j. Also writes a JSON manifest for reproducibility.

Usage:  python -m src.main network
"""

import hashlib
import json
import random
import time
from pathlib import Path

import requests

from src.config import cfg
from src.reference_data import (
    FIRST_NAMES, LAST_NAMES, STREET_NAMES, SUITE_TYPES, ZIP_CODES,
    BUSINESS_SUFFIXES, PAYMENT_TERMS,
)

# ── Sync API base URL ──
SYNC_BASE_URL = "http://localhost:8084"

# ── Industry clusters for the global network ──
# (cluster_name, businesses_list)
# Each business: (name, naics, category, commodities, city, state)

NETWORK_CLUSTERS = {
    "Food & Beverage": {
        "naics_sector": "31",
        "naics_subsector": "311",
        "businesses": [
            ("Hill Country Farms", "111998", "Agriculture", ["organic produce", "vegetables", "herbs"], "Dripping Springs", "TX"),
            ("Lone Star Dairy Co", "112120", "Dairy Production", ["milk", "cheese", "butter"], "Georgetown", "TX"),
            ("Capital City Bakery", "311811", "Bakery", ["bread", "pastries", "cakes"], "Austin", "TX"),
            ("Tex Mex Distributors", "424410", "Food Distribution", ["tortillas", "salsas", "spices"], "San Antonio", "TX"),
            ("BBQ Pit Supply Co", "423440", "Restaurant Supply", ["smokers", "charcoal", "seasoning"], "Austin", "TX"),
            ("Austin Craft Beverages", "312120", "Beverage Manufacturing", ["craft beer", "kombucha", "cold brew"], "Austin", "TX"),
            ("Fresh Catch Seafood", "424460", "Seafood Distribution", ["shrimp", "fish", "oysters"], "Houston", "TX"),
            ("Rio Grande Coffee Roasters", "311920", "Coffee Roasting", ["coffee beans", "espresso", "cold brew"], "Austin", "TX"),
            ("Sunrise Catering Co", "722320", "Catering", ["event catering", "corporate lunch", "buffet"], "Round Rock", "TX"),
            ("Guadalupe Meat Market", "424470", "Meat Distribution", ["beef", "pork", "poultry"], "San Marcos", "TX"),
            ("Pecan Street Wines", "312130", "Wine Distribution", ["wine", "spirits", "craft cocktails"], "Austin", "TX"),
            ("South Congress Cafe Supply", "424410", "Cafe Supply", ["cups", "napkins", "to-go containers"], "Austin", "TX"),
            ("Good Earth Organics", "111419", "Organic Farming", ["organic greens", "microgreens", "sprouts"], "Pflugerville", "TX"),
            ("Bluebonnet Ice Cream", "311520", "Ice Cream Manufacturing", ["ice cream", "gelato", "sorbet"], "Cedar Park", "TX"),
            ("Lone Star Food Trucks", "722330", "Mobile Food", ["food truck rental", "mobile kitchen", "event food"], "Austin", "TX"),
            ("Brazos Valley Honey", "112910", "Apiary", ["raw honey", "beeswax", "honeycomb"], "Georgetown", "TX"),
        ],
    },
    "Technology & SaaS": {
        "naics_sector": "51",
        "naics_subsector": "511",
        "businesses": [
            ("CloudPeak Solutions", "541511", "Software Development", ["cloud hosting", "SaaS platform", "API services"], "Austin", "TX"),
            ("DataBridge Analytics", "541512", "Data Analytics", ["business intelligence", "data warehousing", "dashboards"], "Austin", "TX"),
            ("CyberShield Security", "541512", "Cybersecurity", ["penetration testing", "firewall management", "compliance"], "Dallas", "TX"),
            ("Pixel Perfect Design", "541430", "UX Design", ["web design", "mobile apps", "branding"], "Austin", "TX"),
            ("Circuit Board Labs", "334418", "Electronics Manufacturing", ["PCB assembly", "prototyping", "IoT devices"], "Round Rock", "TX"),
            ("NetWave Communications", "517311", "Telecom", ["fiber internet", "VoIP", "network cabling"], "Austin", "TX"),
            ("Alamo IT Staffing", "561311", "IT Staffing", ["contract developers", "DevOps engineers", "QA analysts"], "San Antonio", "TX"),
            ("StackForge Consulting", "541611", "IT Consulting", ["cloud migration", "system architecture", "DevOps"], "Austin", "TX"),
            ("TrueNode Hosting", "518210", "Cloud Hosting", ["managed hosting", "CDN", "SSL certificates"], "Dallas", "TX"),
            ("Barton Creek Software", "541511", "Custom Software", ["ERP systems", "CRM platforms", "workflow automation"], "Austin", "TX"),
            ("MapPoint GIS Services", "541370", "GIS & Mapping", ["geospatial analysis", "drone mapping", "survey data"], "Cedar Park", "TX"),
            ("Quantum Edge AI", "541715", "AI & Machine Learning", ["NLP models", "computer vision", "predictive analytics"], "Austin", "TX"),
            ("LoneStar Payments", "522320", "Payment Processing", ["credit card processing", "POS systems", "invoicing"], "Houston", "TX"),
            ("RocketLaunch Marketing", "541810", "Digital Marketing", ["SEO", "PPC campaigns", "social media"], "Austin", "TX"),
            ("ByteSmith DevTools", "511210", "Developer Tools", ["IDE plugins", "CI/CD pipelines", "code review"], "Austin", "TX"),
        ],
    },
    "Healthcare & Medical": {
        "naics_sector": "62",
        "naics_subsector": "621",
        "businesses": [
            ("Austin Family Practice", "621111", "Primary Care", ["annual checkups", "vaccinations", "lab work"], "Austin", "TX"),
            ("Lakeway Dental Group", "621210", "Dental", ["cleanings", "fillings", "orthodontics"], "Lakeway", "TX"),
            ("Hill Country Veterinary", "541940", "Veterinary", ["pet wellness", "surgery", "vaccinations"], "Dripping Springs", "TX"),
            ("MedSupply Direct", "423450", "Medical Supply", ["gloves", "syringes", "surgical instruments"], "Houston", "TX"),
            ("BioLab Diagnostics", "621511", "Medical Lab", ["blood tests", "pathology", "urinalysis"], "Austin", "TX"),
            ("PharmaCare Compounding", "446110", "Pharmacy", ["prescriptions", "compounding", "OTC medication"], "Round Rock", "TX"),
            ("ClearView Optometry", "621320", "Optometry", ["eye exams", "contacts", "glasses"], "Cedar Park", "TX"),
            ("Lone Star Physical Therapy", "621340", "Physical Therapy", ["rehab", "sports therapy", "mobility training"], "Austin", "TX"),
            ("Capital Radiology Group", "621512", "Radiology", ["X-rays", "MRI", "CT scans"], "Austin", "TX"),
            ("Premier Home Health", "621610", "Home Health", ["nursing care", "elder care", "post-surgery care"], "Georgetown", "TX"),
            ("Texas Ortho Partners", "621111", "Orthopedics", ["joint replacement", "sports medicine", "fracture care"], "Austin", "TX"),
            ("Bright Smile Pediatric Dental", "621210", "Pediatric Dental", ["children's cleanings", "sealants", "fluoride"], "Pflugerville", "TX"),
            ("Alamo Chiropractic", "621310", "Chiropractic", ["spinal adjustment", "sports rehab", "wellness"], "San Antonio", "TX"),
            ("LifeLine Ambulance", "621910", "Ambulance Services", ["emergency transport", "non-emergency transfer", "event standby"], "Austin", "TX"),
        ],
    },
    "Real Estate & Property": {
        "naics_sector": "53",
        "naics_subsector": "531",
        "businesses": [
            ("Westlake Realty Group", "531210", "Real Estate Brokerage", ["home sales", "buyer representation", "listings"], "Austin", "TX"),
            ("Barton Hills Property Mgmt", "531311", "Property Management", ["tenant screening", "rent collection", "maintenance"], "Austin", "TX"),
            ("LonePoint Commercial", "531120", "Commercial Real Estate", ["office leasing", "retail space", "warehouse"], "Dallas", "TX"),
            ("Zilker Title Company", "541191", "Title Services", ["title search", "escrow", "closing services"], "Austin", "TX"),
            ("Capitol Appraisals", "531320", "Appraisal", ["home appraisal", "commercial valuation", "land assessment"], "Austin", "TX"),
            ("Travis Mortgage Solutions", "522310", "Mortgage", ["home loans", "refinancing", "pre-approval"], "Austin", "TX"),
            ("Gateway Home Inspections", "541350", "Inspection", ["home inspection", "foundation check", "roof inspection"], "Round Rock", "TX"),
            ("Monarch Moving Co", "484210", "Moving Services", ["residential moving", "commercial moving", "packing"], "Austin", "TX"),
            ("Heritage Restoration", "236118", "Restoration", ["historic renovation", "facade restoration", "structural repair"], "San Antonio", "TX"),
            ("Greenfield Land Development", "237210", "Land Development", ["lot clearing", "site grading", "utility install"], "Georgetown", "TX"),
            ("Austin Storage Solutions", "531130", "Storage", ["self storage", "climate controlled", "business storage"], "Austin", "TX"),
            ("SunBelt Roofing & Solar", "238160", "Roofing & Solar", ["roof install", "solar panels", "energy audit"], "Austin", "TX"),
            ("Lockhart Pest Control", "561710", "Pest Control", ["termite treatment", "rodent control", "mosquito spray"], "Kyle", "TX"),
            ("Capitol Pool & Spa", "238990", "Pool Services", ["pool cleaning", "spa repair", "equipment install"], "Austin", "TX"),
        ],
    },
    "Professional Services": {
        "naics_sector": "54",
        "naics_subsector": "541",
        "businesses": [
            ("Pecan Partners CPA", "541211", "Accounting", ["tax preparation", "bookkeeping", "audit"], "Austin", "TX"),
            ("Capitol Law Group", "541110", "Legal", ["business formation", "contracts", "IP law"], "Austin", "TX"),
            ("Amplify Marketing Co", "541810", "Marketing Agency", ["brand strategy", "content marketing", "PR"], "Austin", "TX"),
            ("Ridgeline HR Consulting", "541612", "HR Consulting", ["payroll", "benefits admin", "compliance"], "Round Rock", "TX"),
            ("Benchmark Financial Advisors", "523930", "Financial Advisory", ["retirement planning", "wealth management", "investments"], "Austin", "TX"),
            ("Clearpath Insurance Group", "524210", "Insurance", ["commercial insurance", "workers comp", "liability"], "Dallas", "TX"),
            ("Skyline Architecture", "541310", "Architecture", ["commercial design", "residential plans", "interior design"], "Austin", "TX"),
            ("Verde Environmental", "541620", "Environmental Consulting", ["site assessment", "remediation", "compliance"], "Austin", "TX"),
            ("Pinnacle Staffing", "561311", "Staffing", ["temp staffing", "executive search", "contract placement"], "Houston", "TX"),
            ("Atlas Print & Copy", "323111", "Printing", ["business cards", "brochures", "large format"], "Austin", "TX"),
            ("QuickShip Courier", "492110", "Courier", ["same-day delivery", "document courier", "package delivery"], "Austin", "TX"),
            ("Lonestar Translation", "541930", "Translation", ["document translation", "interpreting", "localization"], "San Antonio", "TX"),
            ("Iron Oak Consulting", "541611", "Management Consulting", ["strategy", "operations", "process improvement"], "Austin", "TX"),
            ("Westbank Notary Services", "541199", "Notary", ["mobile notary", "loan signing", "document notarization"], "Austin", "TX"),
        ],
    },
    "Retail & Wholesale": {
        "naics_sector": "42",
        "naics_subsector": "423",
        "businesses": [
            ("Texas Auto Parts Depot", "423120", "Auto Parts", ["brake pads", "filters", "batteries"], "San Antonio", "TX"),
            ("Southside Office Supply", "424120", "Office Supply", ["paper", "ink cartridges", "furniture"], "Austin", "TX"),
            ("Hill Country Pet Supply", "453910", "Pet Supply", ["dog food", "cat litter", "pet toys"], "Dripping Springs", "TX"),
            ("Capitol Janitorial Supply", "424690", "Cleaning Supply", ["disinfectant", "mops", "trash bags"], "Austin", "TX"),
            ("Austin Uniform Co", "424350", "Uniform Supply", ["work shirts", "safety vests", "boots"], "Austin", "TX"),
            ("RoundTop Furniture", "442110", "Furniture", ["office desks", "chairs", "shelving"], "Round Rock", "TX"),
            ("Fiesta Party Rentals", "532289", "Party Rental", ["tables", "chairs", "tents"], "Austin", "TX"),
            ("SafeGuard Fire & Safety", "423490", "Safety Equipment", ["fire extinguishers", "first aid kits", "hard hats"], "Austin", "TX"),
            ("Greenway Packaging", "424130", "Packaging", ["boxes", "bubble wrap", "tape"], "Kyle", "TX"),
            ("Bluebonnet Gifts & Floral", "453110", "Floral & Gifts", ["flower arrangements", "gift baskets", "event decor"], "Austin", "TX"),
            ("Premier Signage Co", "339950", "Signage", ["business signs", "banners", "vehicle wraps"], "Cedar Park", "TX"),
            ("Central Texas Fuel", "424720", "Fuel Distribution", ["diesel", "gasoline", "propane"], "San Marcos", "TX"),
            ("Maverick Industrial Supply", "423840", "Industrial Supply", ["valves", "fittings", "pumps"], "Houston", "TX"),
            ("Sunset Vending Co", "454210", "Vending", ["snack machines", "beverage machines", "micro-markets"], "Austin", "TX"),
        ],
    },
    "Logistics & Transportation": {
        "naics_sector": "48",
        "naics_subsector": "484",
        "businesses": [
            ("Lone Star Freight", "484121", "Trucking", ["LTL freight", "full truckload", "flatbed"], "San Antonio", "TX"),
            ("Capital Express Logistics", "488510", "Freight Brokerage", ["freight matching", "load booking", "carrier vetting"], "Austin", "TX"),
            ("Gulf Coast Shipping", "483111", "Shipping", ["container shipping", "port logistics", "customs"], "Houston", "TX"),
            ("FleetMaster Auto Repair", "811111", "Fleet Maintenance", ["oil change", "brake service", "tire rotation"], "Austin", "TX"),
            ("AirDrop Drone Delivery", "492110", "Last Mile Delivery", ["drone delivery", "same-day parcels", "medical delivery"], "Austin", "TX"),
            ("CrossRoads Warehousing", "493110", "Warehousing", ["pallet storage", "pick and pack", "inventory management"], "Round Rock", "TX"),
            ("Panhandle Pallet Co", "321920", "Pallet Manufacturing", ["wood pallets", "custom crates", "pallet repair"], "Dallas", "TX"),
            ("Interstate Fuel Services", "447190", "Fuel Services", ["fleet fueling", "fuel cards", "tank monitoring"], "San Antonio", "TX"),
            ("Dispatch Pro Software", "541511", "Fleet Software", ["route optimization", "GPS tracking", "dispatch management"], "Austin", "TX"),
            ("Rio Grande Customs Broker", "488510", "Customs Brokerage", ["import clearance", "tariff classification", "compliance"], "San Antonio", "TX"),
            ("Texan Tow & Recovery", "488410", "Towing", ["roadside assistance", "heavy duty tow", "vehicle recovery"], "Austin", "TX"),
            ("Guadalupe Auto Glass", "811122", "Auto Glass", ["windshield replacement", "chip repair", "tinting"], "San Marcos", "TX"),
            ("I-35 Truck Wash", "811192", "Truck Wash", ["truck wash", "fleet cleaning", "detailing"], "Kyle", "TX"),
        ],
    },
}

# ── Relationship templates: who buys from whom within clusters ──
# (buyer_index, seller_index) within the cluster business list
INTRA_CLUSTER_EDGES = {
    "Food & Beverage": [
        (8, 0), (8, 9), (8, 2),    # Sunrise Catering buys from farms, meat, bakery
        (2, 0), (2, 5),             # Bakery buys from farms, beverages
        (5, 7), (5, 11),            # Beverages buys from coffee roasters, cafe supply
        (14, 8), (14, 9),           # Food trucks buy from catering, meat market
        (10, 3), (10, 6),           # Wines buys from Tex Mex dist, seafood
        (13, 1),                    # Ice cream buys from dairy
        (0, 12),                    # Farms buy from organics
        (7, 3),                     # Coffee roasters buy from distributors
    ],
    "Technology & SaaS": [
        (0, 8), (0, 5),             # CloudPeak buys hosting, telecom
        (1, 0), (1, 8),             # DataBridge buys CloudPeak, hosting
        (2, 8), (2, 5),             # CyberShield buys hosting, telecom
        (3, 0),                     # Pixel Perfect buys CloudPeak
        (9, 0), (9, 6),             # Barton Creek buys CloudPeak, staffing
        (7, 0), (7, 8),             # StackForge buys CloudPeak, hosting
        (11, 0), (11, 1),           # Quantum AI buys CloudPeak, DataBridge
        (13, 3),                    # RocketLaunch buys Pixel Perfect
        (4, 5),                     # Circuit Board buys telecom
        (12, 2),                    # LoneStar Payments buys CyberShield
    ],
    "Healthcare & Medical": [
        (0, 3), (0, 4),             # Family Practice buys supply, labs
        (1, 3),                     # Dental buys supply
        (4, 3),                     # BioLab buys supply
        (5, 3),                     # Pharmacy buys supply
        (6, 3),                     # Optometry buys supply
        (7, 3),                     # PT buys supply
        (8, 3),                     # Radiology buys supply
        (10, 3), (10, 8),           # Ortho buys supply, radiology
        (9, 5),                     # Home Health buys pharmacy
        (11, 3),                    # Pediatric dental buys supply
    ],
    "Real Estate & Property": [
        (0, 3), (0, 4),             # Realty buys title, appraisal
        (1, 6), (1, 11),            # Property Mgmt buys inspection, roofing
        (2, 3), (2, 4),             # Commercial RE buys title, appraisal
        (9, 6),                     # Land Dev buys inspection
        (7, 10),                    # Moving buys storage
        (8, 11),                    # Restoration buys roofing
        (0, 5),                     # Realty uses mortgage
    ],
    "Professional Services": [
        (2, 9),                     # Marketing buys printing
        (2, 10),                    # Marketing buys courier
        (0, 9),                     # CPA buys printing
        (3, 0),                     # HR consulting buys CPA
        (4, 0),                     # Financial buys CPA
        (6, 9),                     # Architecture buys printing
        (12, 0),                    # Iron Oak buys CPA
        (8, 11),                    # Staffing buys translation
    ],
    "Retail & Wholesale": [
        (0, 7),                     # Auto parts buys safety equip
        (1, 8),                     # Office supply buys packaging
        (3, 8),                     # Janitorial buys packaging
        (5, 8),                     # Furniture buys packaging
        (4, 8),                     # Uniform buys packaging
        (6, 10),                    # Party rental buys signage
        (9, 8),                     # Gifts buys packaging
    ],
    "Logistics & Transportation": [
        (0, 3), (0, 7),             # Freight buys fleet maint, fuel
        (1, 0),                     # Express buys freight
        (2, 9),                     # Shipping buys customs broker
        (5, 6),                     # Warehousing buys pallets
        (4, 8),                     # Drone delivery buys dispatch software
        (0, 6),                     # Freight buys pallets
    ],
}

# ── Cross-cluster edges (buyer_cluster, buyer_idx, seller_cluster, seller_idx) ──
CROSS_CLUSTER_EDGES = [
    # Food businesses buy professional services
    ("Food & Beverage", 2, "Professional Services", 0),      # Bakery buys CPA
    ("Food & Beverage", 5, "Professional Services", 2),      # Beverages buys Marketing
    ("Food & Beverage", 8, "Professional Services", 5),      # Catering buys Insurance
    # Tech companies buy professional services
    ("Technology & SaaS", 0, "Professional Services", 1),     # CloudPeak buys Legal
    ("Technology & SaaS", 0, "Professional Services", 0),     # CloudPeak buys CPA
    ("Technology & SaaS", 9, "Professional Services", 1),     # Barton Creek buys Legal
    # Healthcare buys professional + retail
    ("Healthcare & Medical", 0, "Professional Services", 0),  # Family Practice buys CPA
    ("Healthcare & Medical", 0, "Professional Services", 5),  # Family Practice buys Insurance
    ("Healthcare & Medical", 4, "Retail & Wholesale", 3),     # BioLab buys janitorial
    # Real estate buys professional
    ("Real Estate & Property", 0, "Professional Services", 1),  # Realty buys Legal
    ("Real Estate & Property", 1, "Professional Services", 0),  # Property Mgmt buys CPA
    ("Real Estate & Property", 1, "Professional Services", 5),  # Property Mgmt buys Insurance
    # Everyone needs logistics
    ("Retail & Wholesale", 0, "Logistics & Transportation", 0),   # Auto parts buys freight
    ("Retail & Wholesale", 12, "Logistics & Transportation", 2),  # Industrial buys shipping
    ("Food & Beverage", 3, "Logistics & Transportation", 0),      # Tex Mex dist buys freight
    ("Food & Beverage", 6, "Logistics & Transportation", 2),      # Seafood buys shipping
    # Everyone needs office/retail supplies
    ("Technology & SaaS", 0, "Retail & Wholesale", 1),       # CloudPeak buys office supply
    ("Healthcare & Medical", 0, "Retail & Wholesale", 1),    # Family Practice buys office
    ("Professional Services", 1, "Retail & Wholesale", 1),   # Law firm buys office supply
    # Logistics needs tech
    ("Logistics & Transportation", 1, "Technology & SaaS", 0),  # Express buys CloudPeak
    ("Logistics & Transportation", 5, "Technology & SaaS", 1),  # Warehousing buys DataBridge
]


def _golden_id(name):
    """Deterministic golden record ID from business name."""
    h = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"G-{h}"


def _generate_ein():
    prefix = random.choice([74, 75, 76, 82, 83, 84, 46, 47])
    return f"{prefix}-{random.randint(1000000, 9999999)}"


def _generate_contact():
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    return f"{first} {last}", first, last


def _generate_email(first, last, biz_name):
    slug = biz_name.lower().replace(" ", "").replace("&", "").replace("'", "")[:12]
    return random.choice([
        f"{first.lower()}@{slug}.com",
        f"info@{slug}.com",
        f"{first[0].lower()}{last.lower()}@{slug}.com",
    ])


def _generate_phone(area_code="512"):
    return f"({area_code}) {random.randint(200,999)}-{random.randint(1000,9999)}"


def _generate_address(city):
    number = random.randint(100, 19999)
    street = random.choice(STREET_NAMES)
    addr = f"{number} {street}"
    if random.random() < 0.30:
        addr += f", {random.choice(SUITE_TYPES)} {random.randint(1, 400)}"
    return addr


def _get_zip(city):
    return random.choice(ZIP_CODES.get(city, ["78701"]))


def generate_network_businesses():
    """Generate 100 golden records organized by industry cluster."""
    random.seed(cfg.RANDOM_SEED + 1000)  # Different seed from invoice generator

    businesses = []
    for cluster_name, cluster in NETWORK_CLUSTERS.items():
        for name, naics, category, commodities, city, state in cluster["businesses"]:
            contact_full, first, last = _generate_contact()
            area = "512" if state == "TX" and city in ("Austin", "Round Rock", "Cedar Park",
                "Pflugerville", "Georgetown", "Dripping Springs") else "210" if city == "San Antonio" else "713" if city == "Houston" else "214" if city == "Dallas" else "512"

            biz = {
                "golden_record_id": _golden_id(name),
                "canonical_name": name.upper(),
                "name_variants": [name.upper()],
                "cluster": cluster_name,
                "ein": _generate_ein() if random.random() < 0.7 else None,
                "contact_name": contact_full if random.random() < 0.8 else None,
                "email": _generate_email(first, last, name) if random.random() < 0.7 else None,
                "phone_digits": _generate_phone(area) if random.random() < 0.75 else None,
                "naics_code": naics,
                "naics_sector": cluster["naics_sector"],
                "naics_subsector": cluster["naics_subsector"],
                "category": category,
                "commodities": commodities,
                "city": city.upper(),
                "state": state,
                "zip5": _get_zip(city),
                "street_address": _generate_address(city) if random.random() < 0.6 else None,
                "avg_transaction": round(random.uniform(500, 25000), 2),
                "transaction_count": random.randint(10, 200),
                "total_volume": 0,  # computed below
            }
            biz["total_volume"] = round(biz["avg_transaction"] * biz["transaction_count"], 2)
            biz["volume_bracket"] = (
                "HIGH" if biz["total_volume"] > 500000
                else "MEDIUM" if biz["total_volume"] > 100000
                else "LOW"
            )
            businesses.append(biz)

    return businesses


def generate_network_edges(businesses):
    """Generate vendor/client relationship edges between businesses."""
    random.seed(cfg.RANDOM_SEED + 2000)

    # Build lookup: cluster_name -> [businesses in order]
    clusters = {}
    for biz in businesses:
        clusters.setdefault(biz["cluster"], []).append(biz)

    edges = []
    edge_id_counter = 1

    # Intra-cluster edges
    for cluster_name, pairs in INTRA_CLUSTER_EDGES.items():
        cluster_biz = clusters.get(cluster_name, [])
        for buyer_idx, seller_idx in pairs:
            if buyer_idx < len(cluster_biz) and seller_idx < len(cluster_biz):
                buyer = cluster_biz[buyer_idx]
                seller = cluster_biz[seller_idx]
                volume = round(random.uniform(5000, 200000), 2)
                count = random.randint(5, 80)
                edges.append({
                    "edge_id": f"NET-E-{edge_id_counter:04d}",
                    "source_entity_id": buyer["golden_record_id"],
                    "target_entity_id": seller["golden_record_id"],
                    "source_name": buyer["canonical_name"],
                    "target_name": seller["canonical_name"],
                    "rel_type": "BUYS_FROM",
                    "transaction_volume": volume,
                    "transaction_count": count,
                })
                edge_id_counter += 1

    # Cross-cluster edges
    for buyer_cluster, buyer_idx, seller_cluster, seller_idx in CROSS_CLUSTER_EDGES:
        buyer_list = clusters.get(buyer_cluster, [])
        seller_list = clusters.get(seller_cluster, [])
        if buyer_idx < len(buyer_list) and seller_idx < len(seller_list):
            buyer = buyer_list[buyer_idx]
            seller = seller_list[seller_idx]
            volume = round(random.uniform(2000, 80000), 2)
            count = random.randint(3, 40)
            edges.append({
                "edge_id": f"NET-E-{edge_id_counter:04d}",
                "source_entity_id": buyer["golden_record_id"],
                "target_entity_id": seller["golden_record_id"],
                "source_name": buyer["canonical_name"],
                "target_name": seller["canonical_name"],
                "rel_type": "BUYS_FROM",
                "transaction_volume": volume,
                "transaction_count": count,
            })
            edge_id_counter += 1

    return edges


def _build_sync_payload(biz):
    """Build the golden record payload for POST /sync/golden-record."""
    return {
        "golden_record_id": biz["golden_record_id"],
        "canonical_name": biz["canonical_name"],
        "name_variants": biz["name_variants"],
        "persona": {
            "identity": {
                "normalized_name": biz["canonical_name"],
                "name_first_token": biz["canonical_name"].split()[0],
                "name_tokens": biz["canonical_name"].split(),
                "legal_suffix": None,
                "ein_clean": biz.get("ein", "").replace("-", "") if biz.get("ein") else None,
                "phone_digits": biz.get("phone_digits"),
                "email": biz.get("email"),
                "email_domain": biz["email"].split("@")[1] if biz.get("email") else None,
            },
            "industry": {
                "naics_code": biz["naics_code"],
                "naics_sector": biz["naics_sector"],
                "naics_subsector": biz["naics_subsector"],
                "original_category": biz["category"],
                "commodity_keywords": biz["commodities"],
            },
            "location": {
                "state": biz["state"],
                "city_norm": biz["city"],
                "zip3": biz["zip5"][:3] if biz.get("zip5") else None,
                "zip5": biz.get("zip5"),
            },
            "commodity": {
                "top_keywords": biz["commodities"],
                "service_categories": [biz["category"]],
            },
            "behavioral": {
                "volume_bracket": biz.get("volume_bracket"),
                "avg_transaction": biz.get("avg_transaction"),
                "transaction_count": biz.get("transaction_count"),
                "payment_terms": None,
            },
            "sparsity": {
                "identity": 0,
                "industry": 0,
                "location": 0,
                "commodity": 0,
                "behavioral": 0,
            },
        },
        "source_count": 1,
        "confidence": round(random.uniform(0.7, 0.95), 3),
        "status": "ACTIVE",
        "merged_into": None,
        "entity_type": "PHANTOM",
        "source_records": [],
        "bucket_keys": [
            biz["canonical_name"].split()[0].upper(),
            biz.get("ein", "").replace("-", "")[:5] if biz.get("ein") else None,
            biz["city"],
        ],
    }


def sync_to_network(businesses, edges):
    """POST golden records and edges to the MCP sync API."""
    session = requests.Session()
    session.headers["Content-Type"] = "application/json"

    gr_ok, gr_fail = 0, 0
    edge_ok, edge_fail = 0, 0

    print(f"\n  Syncing {len(businesses)} golden records to Neo4j...")
    for biz in businesses:
        payload = _build_sync_payload(biz)
        try:
            r = session.post(f"{SYNC_BASE_URL}/sync/golden-record", json=payload, timeout=10)
            if r.status_code == 200:
                gr_ok += 1
            else:
                gr_fail += 1
                print(f"    FAIL {biz['canonical_name']}: {r.status_code} {r.text[:100]}")
        except Exception as e:
            gr_fail += 1
            print(f"    ERROR {biz['canonical_name']}: {e}")

    print(f"  Golden records: {gr_ok} ok, {gr_fail} failed")

    print(f"\n  Syncing {len(edges)} relationship edges...")
    for edge in edges:
        payload = {
            "edge_id": edge["edge_id"],
            "source_entity_id": edge["source_entity_id"],
            "target_entity_id": edge["target_entity_id"],
            "rel_type": edge["rel_type"],
            "transaction_volume": edge["transaction_volume"],
            "transaction_count": edge["transaction_count"],
        }
        try:
            r = session.post(f"{SYNC_BASE_URL}/sync/relationship", json=payload, timeout=10)
            if r.status_code == 200:
                edge_ok += 1
            else:
                edge_fail += 1
                print(f"    FAIL {edge['edge_id']}: {r.status_code} {r.text[:100]}")
        except Exception as e:
            edge_fail += 1
            print(f"    ERROR {edge['edge_id']}: {e}")

    print(f"  Edges: {edge_ok} ok, {edge_fail} failed")
    return gr_ok, gr_fail, edge_ok, edge_fail


def cmd_network():
    """Generate and seed the Intuit Business Network (Seed 1)."""
    print("=" * 60)
    print("QB Network Graph — Intuit Business Network Seed")
    print("=" * 60)

    # Generate
    print("\nStep 1: Generating global business network...")
    businesses = generate_network_businesses()
    edges = generate_network_edges(businesses)

    cluster_counts = {}
    for b in businesses:
        cluster_counts[b["cluster"]] = cluster_counts.get(b["cluster"], 0) + 1

    print(f"  {len(businesses)} businesses across {len(cluster_counts)} clusters:")
    for cluster, count in cluster_counts.items():
        print(f"    {cluster}: {count}")
    print(f"  {len(edges)} relationship edges")

    # Write manifest
    manifest_dir = cfg.SEED_DIR / "network"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    (manifest_dir / "businesses.json").write_text(
        json.dumps(businesses, indent=2, default=str)
    )
    (manifest_dir / "edges.json").write_text(
        json.dumps(edges, indent=2, default=str)
    )
    print(f"\n  Manifest written to {manifest_dir}/")

    # Sync to Neo4j via MCP sync API
    print("\nStep 2: Syncing to Neo4j via MCP sync API...")
    gr_ok, gr_fail, edge_ok, edge_fail = sync_to_network(businesses, edges)

    print(f"\nSummary:")
    print(f"  Golden records: {gr_ok}/{len(businesses)}")
    print(f"  Edges:          {edge_ok}/{len(edges)}")
    if gr_fail or edge_fail:
        print(f"  Failures:       {gr_fail + edge_fail}")
