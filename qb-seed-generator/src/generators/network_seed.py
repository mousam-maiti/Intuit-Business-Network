"""Seed 1: Intuit Business Network — ~1200 global businesses with relationships.

Generates golden records and inter-business relationships across 12 industry
clusters in 15 metros, then POSTs them to the MCP sync API (port 8084) which
writes to Neo4j.

Uses Faker for realistic business details. Includes mega-hub entities
(wholesaler, bank, cloud provider) that connect to many businesses.

Usage:  python -m src.main network
"""

import hashlib
import json
import random
from pathlib import Path

import requests
from faker import Faker

from src.config import cfg

fake = Faker()
Faker.seed(cfg.RANDOM_SEED + 1000)

SYNC_BASE_URL = "http://localhost:8084"

# ═══════════════════════════════════════════════════════════════
#  METROS & GEOGRAPHY
# ═══════════════════════════════════════════════════════════════

METROS = {
    # city: (state, area_code, zips, weight)
    # weight controls how many businesses spawn here
    "Austin":        ("TX", "512", ["78701","78702","78703","78704","78745","78748","78749","78750","78751","78753","78756","78758","78759"], 12),
    "Houston":       ("TX", "713", ["77001","77002","77003","77008","77019","77027","77030","77056"], 8),
    "Dallas":        ("TX", "214", ["75201","75202","75204","75207","75219","75226","75235"], 7),
    "San Antonio":   ("TX", "210", ["78201","78205","78207","78215","78230","78240","78249"], 6),
    "Round Rock":    ("TX", "512", ["78664","78665","78681"], 3),
    "Cedar Park":    ("TX", "512", ["78613"], 2),
    "Denver":        ("CO", "303", ["80202","80204","80205","80206","80210","80211","80216"], 5),
    "Phoenix":       ("AZ", "602", ["85001","85003","85004","85006","85008","85012","85016"], 5),
    "Los Angeles":   ("CA", "213", ["90001","90012","90015","90017","90024","90028","90036"], 5),
    "San Francisco": ("CA", "415", ["94102","94103","94105","94107","94110","94111","94114"], 4),
    "Chicago":       ("IL", "312", ["60601","60602","60604","60607","60610","60614","60616"], 4),
    "Atlanta":       ("GA", "404", ["30301","30303","30305","30308","30309","30312","30313"], 4),
    "Miami":         ("FL", "305", ["33101","33125","33127","33130","33132","33136","33139"], 4),
    "Seattle":       ("WA", "206", ["98101","98102","98103","98104","98105","98109","98112"], 3),
    "Nashville":     ("TN", "615", ["37201","37203","37206","37208","37210","37211","37212"], 3),
    "Portland":      ("OR", "503", ["97201","97202","97204","97205","97209","97210","97214"], 2),
    "New York":      ("NY", "212", ["10001","10003","10005","10007","10010","10012","10016"], 3),
    "Georgetown":    ("TX", "512", ["78626","78628"], 2),
    "Kyle":          ("TX", "512", ["78640"], 1),
    "San Marcos":    ("TX", "512", ["78666"], 1),
    "Dripping Springs": ("TX", "512", ["78620"], 1),
    "Pflugerville":  ("TX", "512", ["78660"], 1),
}

def _pick_city():
    """Weighted random city selection."""
    cities = list(METROS.keys())
    weights = [METROS[c][3] for c in cities]
    return random.choices(cities, weights=weights, k=1)[0]


# ═══════════════════════════════════════════════════════════════
#  INDUSTRY CLUSTER DEFINITIONS
# ═══════════════════════════════════════════════════════════════

# Each cluster: (name, naics_sector, templates)
# template: (name_pattern, naics_code, category, commodities)
# name_pattern uses {city}, {loc}, {last} as placeholders

CLUSTERS = {
    "Food & Beverage": {
        "naics_sector": "31",
        "count": 100,
        "templates": [
            ("{loc} Farms",              "111998", "Agriculture",        ["organic produce","vegetables","herbs","fruit"]),
            ("{loc} Dairy Co",           "112120", "Dairy Production",   ["milk","cheese","butter","yogurt"]),
            ("{last} Bakery",            "311811", "Bakery",             ["bread","pastries","cakes","cookies"]),
            ("{loc} Distributors",       "424410", "Food Distribution",  ["tortillas","salsas","spices","canned goods"]),
            ("{loc} Restaurant Supply",  "423440", "Restaurant Supply",  ["smokers","charcoal","cookware","utensils"]),
            ("{loc} Beverages",          "312120", "Beverage Mfg",       ["craft beer","kombucha","cold brew","soda"]),
            ("{loc} Seafood",            "424460", "Seafood",            ["shrimp","fish","oysters","crab"]),
            ("{last} Coffee Roasters",   "311920", "Coffee",             ["coffee beans","espresso","cold brew","tea"]),
            ("{loc} Catering",           "722320", "Catering",           ["event catering","corporate lunch","buffet"]),
            ("{loc} Meat Market",        "424470", "Meat Distribution",  ["beef","pork","poultry","sausage"]),
            ("{loc} Wines & Spirits",    "312130", "Wine Distribution",  ["wine","spirits","craft cocktails"]),
            ("{last} Ice Cream Co",      "311520", "Ice Cream",          ["ice cream","gelato","sorbet","frozen yogurt"]),
            ("{loc} Food Trucks",        "722330", "Mobile Food",        ["food truck rental","mobile kitchen","event food"]),
            ("{loc} Organics",           "111419", "Organic Farming",    ["organic greens","microgreens","sprouts"]),
        ],
    },
    "Technology & SaaS": {
        "naics_sector": "54",
        "count": 100,
        "templates": [
            ("{loc} Software",           "541511", "Software Dev",       ["SaaS platform","API services","web apps"]),
            ("{loc} Analytics",          "541512", "Data Analytics",     ["business intelligence","dashboards","data warehousing"]),
            ("{loc} Cybersecurity",      "541512", "Cybersecurity",      ["penetration testing","firewall mgmt","compliance"]),
            ("{last} Design Studio",     "541430", "UX Design",          ["web design","mobile apps","branding"]),
            ("{loc} IT Staffing",        "561311", "IT Staffing",        ["contract developers","DevOps engineers","QA"]),
            ("{last} Consulting",        "541611", "IT Consulting",      ["cloud migration","system architecture","DevOps"]),
            ("{loc} Cloud Hosting",      "518210", "Cloud Hosting",      ["managed hosting","CDN","SSL certificates"]),
            ("{loc} AI Labs",            "541715", "AI & ML",            ["NLP models","computer vision","predictive analytics"]),
            ("{loc} Payments",           "522320", "Payment Processing", ["credit card processing","POS systems","invoicing"]),
            ("{last} Marketing Digital", "541810", "Digital Marketing",  ["SEO","PPC campaigns","social media"]),
            ("{loc} DevTools",           "511210", "Developer Tools",    ["IDE plugins","CI/CD pipelines","code review"]),
            ("{loc} IoT Systems",        "334418", "Electronics Mfg",    ["PCB assembly","IoT devices","prototyping"]),
        ],
    },
    "Healthcare & Medical": {
        "naics_sector": "62",
        "count": 100,
        "templates": [
            ("{loc} Family Practice",    "621111", "Primary Care",       ["annual checkups","vaccinations","lab work"]),
            ("{loc} Dental Group",       "621210", "Dental",             ["cleanings","fillings","orthodontics"]),
            ("{loc} Veterinary",         "541940", "Veterinary",         ["pet wellness","surgery","vaccinations"]),
            ("{loc} Medical Supply",     "423450", "Medical Supply",     ["gloves","syringes","surgical instruments"]),
            ("{loc} Diagnostics Lab",    "621511", "Medical Lab",        ["blood tests","pathology","urinalysis"]),
            ("{last} Pharmacy",          "446110", "Pharmacy",           ["prescriptions","compounding","OTC medication"]),
            ("{loc} Optometry",          "621320", "Optometry",          ["eye exams","contacts","glasses"]),
            ("{loc} Physical Therapy",   "621340", "Physical Therapy",   ["rehab","sports therapy","mobility training"]),
            ("{loc} Radiology",          "621512", "Radiology",          ["X-rays","MRI","CT scans"]),
            ("{loc} Home Health",        "621610", "Home Health",        ["nursing care","elder care","post-surgery"]),
            ("{loc} Chiropractic",       "621310", "Chiropractic",       ["spinal adjustment","sports rehab","wellness"]),
            ("{loc} Ambulance Service",  "621910", "Ambulance",          ["emergency transport","non-emergency transfer"]),
        ],
    },
    "Real Estate & Property": {
        "naics_sector": "53",
        "count": 100,
        "templates": [
            ("{loc} Realty Group",       "531210", "Real Estate",        ["home sales","buyer representation","listings"]),
            ("{loc} Property Mgmt",      "531311", "Property Mgmt",      ["tenant screening","rent collection","maintenance"]),
            ("{loc} Commercial RE",      "531120", "Commercial RE",      ["office leasing","retail space","warehouse"]),
            ("{loc} Title Company",      "541191", "Title Services",     ["title search","escrow","closing services"]),
            ("{loc} Appraisals",         "531320", "Appraisal",          ["home appraisal","commercial valuation"]),
            ("{loc} Mortgage",           "522310", "Mortgage",           ["home loans","refinancing","pre-approval"]),
            ("{loc} Home Inspections",   "541350", "Inspection",         ["home inspection","foundation check","roof inspection"]),
            ("{last} Moving Co",         "484210", "Moving Services",    ["residential moving","commercial moving","packing"]),
            ("{loc} Restoration",        "236118", "Restoration",        ["historic renovation","facade restoration"]),
            ("{loc} Land Development",   "237210", "Land Development",   ["lot clearing","site grading","utility install"]),
            ("{loc} Storage Solutions",  "531130", "Storage",            ["self storage","climate controlled","business storage"]),
            ("{loc} Roofing & Solar",    "238160", "Roofing & Solar",    ["roof install","solar panels","energy audit"]),
            ("{loc} Pool & Spa",         "238990", "Pool Services",      ["pool cleaning","spa repair","equipment install"]),
        ],
    },
    "Professional Services": {
        "naics_sector": "54",
        "count": 100,
        "templates": [
            ("{last} CPA Group",         "541211", "Accounting",         ["tax preparation","bookkeeping","audit","payroll"]),
            ("{last} Law Group",         "541110", "Legal",              ["business formation","contracts","IP law","litigation"]),
            ("{loc} Marketing Agency",   "541810", "Marketing",          ["brand strategy","content marketing","PR"]),
            ("{loc} HR Consulting",      "541612", "HR Consulting",      ["payroll","benefits admin","compliance"]),
            ("{loc} Financial Advisors", "523930", "Financial Advisory", ["retirement planning","wealth management"]),
            ("{loc} Insurance Group",    "524210", "Insurance",          ["commercial insurance","workers comp","liability"]),
            ("{loc} Architecture",       "541310", "Architecture",       ["commercial design","residential plans"]),
            ("{loc} Environmental",      "541620", "Environmental",      ["site assessment","remediation","compliance"]),
            ("{loc} Staffing",           "561311", "Staffing",           ["temp staffing","executive search","placement"]),
            ("{loc} Print & Copy",       "323111", "Printing",           ["business cards","brochures","large format"]),
            ("{last} Translation Svc",   "541930", "Translation",        ["document translation","interpreting","localization"]),
            ("{loc} Notary Services",    "541199", "Notary",             ["mobile notary","loan signing","document notarization"]),
        ],
    },
    "Retail & Wholesale": {
        "naics_sector": "42",
        "count": 100,
        "templates": [
            ("{loc} Auto Parts",         "423120", "Auto Parts",         ["brake pads","filters","batteries","tires"]),
            ("{loc} Office Supply",      "424120", "Office Supply",      ["paper","ink cartridges","furniture","stationery"]),
            ("{loc} Pet Supply",         "453910", "Pet Supply",         ["dog food","cat litter","pet toys","grooming"]),
            ("{loc} Janitorial Supply",  "424690", "Cleaning Supply",    ["disinfectant","mops","trash bags","sanitizer"]),
            ("{loc} Uniform Co",         "424350", "Uniform Supply",     ["work shirts","safety vests","boots","hardhats"]),
            ("{loc} Furniture",          "442110", "Furniture",          ["office desks","chairs","shelving","file cabinets"]),
            ("{loc} Party Rentals",      "532289", "Party Rental",       ["tables","chairs","tents","linens"]),
            ("{loc} Safety Equipment",   "423490", "Safety Equipment",   ["fire extinguishers","first aid kits","PPE"]),
            ("{loc} Packaging",          "424130", "Packaging",          ["boxes","bubble wrap","tape","poly bags"]),
            ("{loc} Signage",            "339950", "Signage",            ["business signs","banners","vehicle wraps"]),
            ("{loc} Fuel",               "424720", "Fuel Distribution",  ["diesel","gasoline","propane","lubricants"]),
            ("{loc} Industrial Supply",  "423840", "Industrial Supply",  ["valves","fittings","pumps","motors"]),
        ],
    },
    "Logistics & Transportation": {
        "naics_sector": "48",
        "count": 80,
        "templates": [
            ("{loc} Freight",            "484121", "Trucking",           ["LTL freight","full truckload","flatbed"]),
            ("{loc} Logistics",          "488510", "Freight Brokerage",  ["freight matching","load booking","carrier vetting"]),
            ("{loc} Shipping",           "483111", "Shipping",           ["container shipping","port logistics","customs"]),
            ("{loc} Fleet Repair",       "811111", "Fleet Maintenance",  ["oil change","brake service","tire rotation"]),
            ("{loc} Drone Delivery",     "492110", "Last Mile Delivery", ["drone delivery","same-day parcels","medical delivery"]),
            ("{loc} Warehousing",        "493110", "Warehousing",        ["pallet storage","pick and pack","inventory mgmt"]),
            ("{loc} Courier",            "492110", "Courier",            ["same-day delivery","document courier","package delivery"]),
            ("{loc} Towing",             "488410", "Towing",             ["roadside assistance","heavy duty tow","vehicle recovery"]),
        ],
    },
    "Education & Training": {
        "naics_sector": "61",
        "count": 80,
        "templates": [
            ("{loc} Academy",            "611110", "K-12 Education",     ["curriculum","tutoring","after-school programs"]),
            ("{loc} Trade School",       "611519", "Trade Education",    ["welding cert","HVAC training","electrical apprentice"]),
            ("{loc} Language School",    "611630", "Language Training",  ["ESL classes","Spanish courses","business English"]),
            ("{loc} Music Academy",      "611610", "Music Education",    ["piano lessons","guitar","voice coaching"]),
            ("{loc} Test Prep",          "611691", "Test Preparation",   ["SAT prep","GRE tutoring","professional cert"]),
            ("{loc} Driving School",     "611692", "Driving School",     ["drivers ed","CDL training","defensive driving"]),
            ("{last} Tutoring",          "611691", "Tutoring",           ["math tutoring","science","reading comprehension"]),
            ("{loc} Childcare Center",   "624410", "Childcare",          ["daycare","preschool","after-school care"]),
        ],
    },
    "Manufacturing": {
        "naics_sector": "33",
        "count": 80,
        "templates": [
            ("{loc} Metal Fabrication",  "332312", "Metal Fabrication",  ["steel beams","custom metalwork","welding"]),
            ("{loc} Plastics",           "326199", "Plastics Mfg",       ["injection molding","custom plastics","packaging"]),
            ("{loc} Woodworking",        "337110", "Wood Products",      ["cabinets","custom furniture","millwork"]),
            ("{loc} Machine Shop",       "332710", "Machine Shop",       ["CNC machining","precision parts","prototyping"]),
            ("{loc} Textiles",           "313210", "Textiles",           ["fabric","upholstery","industrial textiles"]),
            ("{loc} Chemical Supply",    "325998", "Chemical Mfg",       ["industrial chemicals","solvents","adhesives"]),
            ("{loc} Packaging Mfg",      "322211", "Packaging Mfg",      ["corrugated boxes","custom packaging","labels"]),
            ("{loc} Tool & Die",         "333514", "Tool & Die",         ["custom tooling","die casting","mold making"]),
        ],
    },
    "Energy & Utilities": {
        "naics_sector": "22",
        "count": 60,
        "templates": [
            ("{loc} Solar",              "221114", "Solar Energy",       ["solar panels","installation","energy storage"]),
            ("{loc} Electric Co-op",     "221122", "Electric Utility",   ["power distribution","grid maintenance"]),
            ("{loc} Wind Energy",        "221115", "Wind Energy",        ["wind turbines","maintenance","monitoring"]),
            ("{loc} Energy Consulting",  "541690", "Energy Consulting",  ["energy audit","efficiency","carbon offset"]),
            ("{loc} HVAC Services",      "238220", "HVAC Services",      ["AC install","heating repair","duct cleaning"]),
            ("{loc} Electrical Services","238210", "Electrical Services", ["panel upgrades","wiring","lighting install"]),
        ],
    },
    "Government & Civic": {
        "naics_sector": "92",
        "count": 60,
        "templates": [
            ("{loc} Public Works",       "237310", "Public Works",       ["road repair","bridge maintenance","utility"]),
            ("{loc} Parks & Recreation", "712190", "Parks & Rec",        ["park maintenance","facility mgmt","events"]),
            ("{loc} Water District",     "221310", "Water Utility",      ["water treatment","pipe maintenance","metering"]),
            ("{loc} Transit Authority",  "485111", "Public Transit",     ["bus service","route planning","fleet maintenance"]),
            ("{loc} Housing Authority",  "925110", "Public Housing",     ["affordable housing","property maintenance"]),
            ("{loc} Fire Department",    "922160", "Fire Protection",    ["fire response","inspections","prevention"]),
        ],
    },
    "Entertainment & Hospitality": {
        "naics_sector": "71",
        "count": 60,
        "templates": [
            ("{loc} Event Venue",        "713990", "Event Venue",        ["wedding venue","conference center","banquet hall"]),
            ("{loc} Hotels",             "721110", "Lodging",            ["hotel rooms","conference rooms","banquet"]),
            ("{loc} Fitness Center",     "713940", "Fitness",            ["gym membership","personal training","group classes"]),
            ("{loc} Photography",        "541922", "Photography",        ["event photography","portraits","commercial"]),
            ("{loc} DJ & Entertainment", "711510", "Entertainment",      ["live music","DJ services","event planning"]),
            ("{last} Brewing Co",        "312120", "Brewery",            ["craft beer","taproom","brewery tours"]),
        ],
    },
}

# ═══════════════════════════════════════════════════════════════
#  MEGA-HUB ENTITIES (high degree — connect to many businesses)
# ═══════════════════════════════════════════════════════════════

MEGA_HUBS = [
    {
        "name": "COSTCO BUSINESS CENTER",
        "naics": "452910", "category": "Wholesale Club",
        "commodities": ["bulk supplies","office supplies","cleaning products","food service","electronics"],
        "city": "Austin", "state": "TX",
        "connect_pct": 0.15,  # 15% of all businesses buy from Costco
        "clusters": None,  # all clusters
    },
    {
        "name": "CHASE BUSINESS BANKING",
        "naics": "522110", "category": "Commercial Banking",
        "commodities": ["business checking","merchant services","business loans","payroll","credit lines"],
        "city": "Dallas", "state": "TX",
        "connect_pct": 0.12,
        "clusters": None,
    },
    {
        "name": "AWS CLOUD SERVICES",
        "naics": "518210", "category": "Cloud Infrastructure",
        "commodities": ["cloud compute","S3 storage","RDS databases","Lambda","CloudFront CDN"],
        "city": "Seattle", "state": "WA",
        "connect_pct": 0.08,
        "clusters": ["Technology & SaaS", "Healthcare & Medical", "Manufacturing"],
    },
    {
        "name": "UNITED PARCEL SERVICE",
        "naics": "492110", "category": "Package Delivery",
        "commodities": ["ground shipping","express delivery","freight","returns management"],
        "city": "Atlanta", "state": "GA",
        "connect_pct": 0.10,
        "clusters": ["Retail & Wholesale", "Food & Beverage", "Manufacturing", "Healthcare & Medical"],
    },
    {
        "name": "ADP WORKFORCE SOLUTIONS",
        "naics": "541214", "category": "Payroll Services",
        "commodities": ["payroll processing","HR management","tax filing","benefits admin"],
        "city": "New York", "state": "NY",
        "connect_pct": 0.07,
        "clusters": None,
    },
    {
        "name": "GRAINGER INDUSTRIAL SUPPLY",
        "naics": "423840", "category": "Industrial MRO",
        "commodities": ["motors","pumps","safety gear","hand tools","fasteners","electrical"],
        "city": "Chicago", "state": "IL",
        "connect_pct": 0.10,
        "clusters": ["Manufacturing", "Energy & Utilities", "Logistics & Transportation", "Government & Civic"],
    },
]

# ═══════════════════════════════════════════════════════════════
#  CROSS-CLUSTER BUYING RULES
# ═══════════════════════════════════════════════════════════════
# (buyer_cluster, seller_cluster, probability)
# "X% of businesses in buyer_cluster buy from a random business in seller_cluster"

CROSS_CLUSTER_RULES = [
    # Everyone needs professional services
    ("Food & Beverage",           "Professional Services", 0.25),
    ("Technology & SaaS",         "Professional Services", 0.30),
    ("Healthcare & Medical",      "Professional Services", 0.25),
    ("Real Estate & Property",    "Professional Services", 0.30),
    ("Retail & Wholesale",        "Professional Services", 0.20),
    ("Logistics & Transportation","Professional Services", 0.15),
    ("Manufacturing",             "Professional Services", 0.20),
    ("Education & Training",      "Professional Services", 0.15),
    ("Energy & Utilities",        "Professional Services", 0.15),
    ("Entertainment & Hospitality","Professional Services", 0.20),
    # Many need logistics
    ("Food & Beverage",           "Logistics & Transportation", 0.20),
    ("Retail & Wholesale",        "Logistics & Transportation", 0.25),
    ("Manufacturing",             "Logistics & Transportation", 0.30),
    ("Healthcare & Medical",      "Logistics & Transportation", 0.10),
    # Tech is horizontal
    ("Healthcare & Medical",      "Technology & SaaS",    0.15),
    ("Real Estate & Property",    "Technology & SaaS",    0.12),
    ("Retail & Wholesale",        "Technology & SaaS",    0.10),
    ("Logistics & Transportation","Technology & SaaS",    0.15),
    ("Manufacturing",             "Technology & SaaS",    0.12),
    ("Education & Training",      "Technology & SaaS",    0.10),
    ("Entertainment & Hospitality","Technology & SaaS",   0.08),
    # Retail supplies
    ("Food & Beverage",           "Retail & Wholesale",   0.15),
    ("Healthcare & Medical",      "Retail & Wholesale",   0.12),
    ("Education & Training",      "Retail & Wholesale",   0.10),
    ("Entertainment & Hospitality","Retail & Wholesale",  0.12),
    # Real estate / property
    ("Entertainment & Hospitality","Real Estate & Property", 0.10),
    ("Healthcare & Medical",      "Real Estate & Property",  0.08),
    ("Education & Training",      "Real Estate & Property",  0.08),
    # Energy
    ("Manufacturing",             "Energy & Utilities",   0.12),
    ("Real Estate & Property",    "Energy & Utilities",   0.10),
]

# ═══════════════════════════════════════════════════════════════
#  GENERATION
# ═══════════════════════════════════════════════════════════════

def _golden_id(name):
    h = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"G-{h}"


def _gen_ein():
    prefix = random.choice([74,75,76,82,83,84,46,47,27,36,45,61,62,73,81,91,92,93,94,95])
    return f"{prefix}-{random.randint(1000000, 9999999)}"


def _gen_phone(area_code):
    return f"({area_code}) {random.randint(200,999)}-{random.randint(1000,9999)}"


def _gen_email(biz_name):
    slug = biz_name.lower().replace(" ","").replace("&","").replace("'","")[:14]
    prefix = random.choice(["info","contact","sales","hello","admin","office"])
    return f"{prefix}@{slug}.com"


def _loc_descriptor(city):
    """Generate a location-based business name prefix."""
    descriptors = {
        "Austin": ["Austin","ATX","Capital City","Congress Ave","South Austin","Barton Creek"],
        "Houston": ["Houston","Gulf Coast","Bayou City","Space City","Heights"],
        "Dallas": ["Dallas","North Texas","Trinity","Big D","Uptown"],
        "San Antonio": ["San Antonio","Alamo City","River Walk","Mission City"],
        "Round Rock": ["Round Rock","Brushy Creek"],
        "Cedar Park": ["Cedar Park","Lakeline"],
        "Denver": ["Denver","Mile High","Front Range","Rocky Mountain","Colorado"],
        "Phoenix": ["Phoenix","Valley","Sonoran","Desert","Southwest"],
        "Los Angeles": ["Los Angeles","Pacific","West Coast","SoCal","Sunset"],
        "San Francisco": ["San Francisco","Bay Area","Golden Gate","Pacific","Marina"],
        "Chicago": ["Chicago","Windy City","Lakeside","Midwest","Loop"],
        "Atlanta": ["Atlanta","Peachtree","Southern","Buckhead","Piedmont"],
        "Miami": ["Miami","South Beach","Biscayne","Coral","Tropical"],
        "Seattle": ["Seattle","Puget Sound","Emerald City","Pacific NW","Cascade"],
        "Nashville": ["Nashville","Music City","Cumberland","Southern","Volunteer"],
        "Portland": ["Portland","Rose City","Pacific NW","Willamette","Cascadia"],
        "New York": ["New York","Metro","Empire","Manhattan","Tri-State"],
        "Georgetown": ["Georgetown","Sun City"],
        "Kyle": ["Kyle","Plum Creek"],
        "San Marcos": ["San Marcos","Bobcat"],
        "Dripping Springs": ["Dripping Springs","Hill Country"],
        "Pflugerville": ["Pflugerville","Blackhawk"],
    }
    return random.choice(descriptors.get(city, [city]))


def generate_network_businesses():
    """Generate ~1200 golden records organized by industry cluster."""
    random.seed(cfg.RANDOM_SEED + 1000)

    businesses = []
    used_names = set()

    for cluster_name, cluster_def in CLUSTERS.items():
        target_count = cluster_def["count"]
        templates = cluster_def["templates"]
        generated = 0

        while generated < target_count:
            template = random.choice(templates)
            name_pattern, naics, category, commodities = template

            city = _pick_city()
            state, area_code, zips, _ = METROS[city]
            loc = _loc_descriptor(city)
            last = fake.last_name()

            raw_name = name_pattern.format(loc=loc, city=city, last=last)
            canonical = raw_name.upper()

            if canonical in used_names:
                continue
            used_names.add(canonical)

            has_ein = random.random() < 0.70
            has_contact = random.random() < 0.75
            has_email = random.random() < 0.70
            has_phone = random.random() < 0.75

            contact_name = fake.name() if has_contact else None

            # Pick 2-3 commodities from template + add 0-1 random
            n_comm = random.randint(2, min(4, len(commodities)))
            biz_commodities = random.sample(commodities, n_comm)

            avg_txn = round(random.uniform(500, 30000), 2)
            txn_count = random.randint(8, 250)
            total_vol = round(avg_txn * txn_count, 2)

            biz = {
                "golden_record_id": _golden_id(raw_name),
                "canonical_name": canonical,
                "name_variants": [canonical],
                "cluster": cluster_name,
                "ein": _gen_ein() if has_ein else None,
                "contact_name": contact_name,
                "email": _gen_email(raw_name) if has_email else None,
                "phone_digits": _gen_phone(area_code) if has_phone else None,
                "naics_code": naics,
                "naics_sector": cluster_def["naics_sector"],
                "category": category,
                "commodities": biz_commodities,
                "city": city.upper(),
                "state": state,
                "zip5": random.choice(zips),
                "street_address": fake.street_address() if random.random() < 0.55 else None,
                "avg_transaction": avg_txn,
                "transaction_count": txn_count,
                "total_volume": total_vol,
                "volume_bracket": "HIGH" if total_vol > 500000 else "MEDIUM" if total_vol > 100000 else "LOW",
                "confidence": round(random.uniform(0.65, 0.98), 3),
            }
            businesses.append(biz)
            generated += 1

    # ── Add mega-hub entities ──
    for hub in MEGA_HUBS:
        canonical = hub["name"]
        if canonical in used_names:
            continue
        used_names.add(canonical)

        state = hub["state"]
        city = hub["city"]
        metro = METROS.get(city, ("TX","512",["78701"],1))

        biz = {
            "golden_record_id": _golden_id(hub["name"]),
            "canonical_name": canonical,
            "name_variants": [canonical],
            "cluster": "Mega-Hub",
            "ein": _gen_ein(),
            "contact_name": fake.name(),
            "email": _gen_email(hub["name"]),
            "phone_digits": _gen_phone(metro[1]),
            "naics_code": hub["naics"],
            "naics_sector": hub["naics"][:2],
            "category": hub["category"],
            "commodities": hub["commodities"],
            "city": city.upper(),
            "state": state,
            "zip5": random.choice(metro[2]),
            "street_address": fake.street_address(),
            "avg_transaction": round(random.uniform(2000, 50000), 2),
            "transaction_count": random.randint(100, 500),
            "total_volume": 0,
            "volume_bracket": "HIGH",
            "confidence": round(random.uniform(0.95, 0.99), 3),
        }
        biz["total_volume"] = round(biz["avg_transaction"] * biz["transaction_count"], 2)
        businesses.append(biz)

    return businesses


def generate_network_edges(businesses):
    """Generate relationship edges using probabilistic rules."""
    random.seed(cfg.RANDOM_SEED + 2000)

    # Build cluster lookup
    clusters = {}
    biz_by_id = {}
    for biz in businesses:
        clusters.setdefault(biz["cluster"], []).append(biz)
        biz_by_id[biz["golden_record_id"]] = biz

    edges = []
    edge_set = set()  # avoid duplicates
    eid = 1

    def _add_edge(buyer, seller, vol=None, cnt=None):
        nonlocal eid
        key = (buyer["golden_record_id"], seller["golden_record_id"])
        if key in edge_set or key[0] == key[1]:
            return
        edge_set.add(key)
        edges.append({
            "edge_id": f"NET-E-{eid:05d}",
            "source_entity_id": buyer["golden_record_id"],
            "target_entity_id": seller["golden_record_id"],
            "source_name": buyer["canonical_name"],
            "target_name": seller["canonical_name"],
            "rel_type": "BUYS_FROM",
            "transaction_volume": vol or round(random.uniform(2000, 200000), 2),
            "transaction_count": cnt or random.randint(3, 80),
        })
        eid += 1

    # ── 1. Intra-cluster edges ──
    # Each business buys from 1-4 others in its cluster
    for cluster_name, cluster_biz in clusters.items():
        if cluster_name == "Mega-Hub":
            continue
        for biz in cluster_biz:
            # Pick 1-4 suppliers within the same cluster
            n_suppliers = random.randint(1, min(4, len(cluster_biz) - 1))
            potential = [b for b in cluster_biz if b["golden_record_id"] != biz["golden_record_id"]]
            if potential:
                suppliers = random.sample(potential, min(n_suppliers, len(potential)))
                for supplier in suppliers:
                    _add_edge(biz, supplier)

    # ── 2. Cross-cluster edges ──
    for buyer_cluster, seller_cluster, prob in CROSS_CLUSTER_RULES:
        buyer_list = clusters.get(buyer_cluster, [])
        seller_list = clusters.get(seller_cluster, [])
        if not seller_list:
            continue
        for buyer in buyer_list:
            if random.random() < prob:
                seller = random.choice(seller_list)
                _add_edge(buyer, seller)

    # ── 3. Mega-hub edges ──
    all_non_hub = [b for b in businesses if b["cluster"] != "Mega-Hub"]
    for hub_def in MEGA_HUBS:
        hub_biz = biz_by_id.get(_golden_id(hub_def["name"]))
        if not hub_biz:
            continue

        target_clusters = hub_def["clusters"]
        candidates = all_non_hub if target_clusters is None else [
            b for b in all_non_hub if b["cluster"] in target_clusters
        ]

        for candidate in candidates:
            if random.random() < hub_def["connect_pct"]:
                _add_edge(candidate, hub_biz)

    return edges


# ═══════════════════════════════════════════════════════════════
#  SYNC TO NEO4J
# ═══════════════════════════════════════════════════════════════

def _build_sync_payload(biz):
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
                "ein_clean": biz["ein"].replace("-","") if biz.get("ein") else None,
                "phone_digits": biz.get("phone_digits"),
                "email": biz.get("email"),
                "email_domain": biz["email"].split("@")[1] if biz.get("email") else None,
            },
            "industry": {
                "naics_code": biz["naics_code"],
                "naics_sector": biz["naics_sector"],
                "naics_subsector": biz["naics_code"][:3] if biz.get("naics_code") else None,
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
        "confidence": biz.get("confidence", 0.80),
        "status": "ACTIVE",
        "merged_into": None,
        "entity_type": "PHANTOM",
        "source_records": [],
        "bucket_keys": [
            biz["canonical_name"].split()[0].upper(),
            biz["ein"].replace("-","")[:5] if biz.get("ein") else None,
            biz["city"],
        ],
    }


def sync_to_network(businesses, edges):
    session = requests.Session()
    session.headers["Content-Type"] = "application/json"

    gr_ok, gr_fail = 0, 0
    edge_ok, edge_fail = 0, 0

    print(f"\n  Syncing {len(businesses)} golden records to Neo4j...")
    for i, biz in enumerate(businesses):
        payload = _build_sync_payload(biz)
        try:
            r = session.post(f"{SYNC_BASE_URL}/sync/golden-record", json=payload, timeout=10)
            if r.status_code == 200:
                gr_ok += 1
            else:
                gr_fail += 1
                if gr_fail <= 5:
                    print(f"    FAIL {biz['canonical_name']}: {r.status_code} {r.text[:100]}")
        except Exception as e:
            gr_fail += 1
            if gr_fail <= 5:
                print(f"    ERROR {biz['canonical_name']}: {e}")

        if (i + 1) % 100 == 0:
            print(f"    ... {i+1}/{len(businesses)} records synced")

    print(f"  Golden records: {gr_ok} ok, {gr_fail} failed")

    print(f"\n  Syncing {len(edges)} relationship edges...")
    for i, edge in enumerate(edges):
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
                if edge_fail <= 5:
                    print(f"    FAIL {edge['edge_id']}: {r.status_code} {r.text[:100]}")
        except Exception as e:
            edge_fail += 1
            if edge_fail <= 5:
                print(f"    ERROR {edge['edge_id']}: {e}")

        if (i + 1) % 500 == 0:
            print(f"    ... {i+1}/{len(edges)} edges synced")

    print(f"  Edges: {edge_ok} ok, {edge_fail} failed")
    return gr_ok, gr_fail, edge_ok, edge_fail


def cmd_network():
    """Generate and seed the Intuit Business Network."""
    print("=" * 60)
    print("QB Network Graph — Intuit Business Network Seed")
    print("=" * 60)

    print("\nStep 1: Generating global business network...")
    businesses = generate_network_businesses()
    edges = generate_network_edges(businesses)

    # Stats
    cluster_counts = {}
    city_counts = {}
    state_counts = {}
    for b in businesses:
        cluster_counts[b["cluster"]] = cluster_counts.get(b["cluster"], 0) + 1
        city_counts[b["city"]] = city_counts.get(b["city"], 0) + 1
        state_counts[b["state"]] = state_counts.get(b["state"], 0) + 1

    print(f"  {len(businesses)} businesses across {len(cluster_counts)} clusters:")
    for cluster, count in sorted(cluster_counts.items(), key=lambda x: -x[1]):
        print(f"    {cluster:35s} {count:4d}")

    print(f"\n  Geographic spread: {len(state_counts)} states, {len(city_counts)} cities")
    for state, count in sorted(state_counts.items(), key=lambda x: -x[1])[:8]:
        print(f"    {state}: {count}")

    print(f"\n  {len(edges)} relationship edges")

    # Degree distribution
    degree = {}
    for e in edges:
        degree[e["source_entity_id"]] = degree.get(e["source_entity_id"], 0) + 1
        degree[e["target_entity_id"]] = degree.get(e["target_entity_id"], 0) + 1

    buckets = {"0": 0, "1-2": 0, "3-5": 0, "6-10": 0, "11-20": 0, "21+": 0}
    for b in businesses:
        d = degree.get(b["golden_record_id"], 0)
        if d == 0: buckets["0"] += 1
        elif d <= 2: buckets["1-2"] += 1
        elif d <= 5: buckets["3-5"] += 1
        elif d <= 10: buckets["6-10"] += 1
        elif d <= 20: buckets["11-20"] += 1
        else: buckets["21+"] += 1

    print(f"\n  Degree distribution:")
    for bucket, count in buckets.items():
        print(f"    {bucket:6s} connections: {count:4d} entities")

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

    # Sync to Neo4j
    print("\nStep 2: Syncing to Neo4j via MCP sync API...")
    gr_ok, gr_fail, edge_ok, edge_fail = sync_to_network(businesses, edges)

    print(f"\nSummary:")
    print(f"  Golden records: {gr_ok}/{len(businesses)}")
    print(f"  Edges:          {edge_ok}/{len(edges)}")
    if gr_fail or edge_fail:
        print(f"  Failures:       {gr_fail + edge_fail}")
