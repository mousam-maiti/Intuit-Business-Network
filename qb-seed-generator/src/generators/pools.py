"""Generate ground truth vendor and client pools.

Each entry represents a REAL-WORLD business with canonical data.
When assigned to QB accounts later, display names get varied.
"""

import random
from src.config import cfg
from src.reference_data import (
    FIRST_NAMES, LAST_NAMES, LOCATION_DESCRIPTORS, BUSINESS_SUFFIXES,
    STREET_NAMES, SUITE_TYPES, ZIP_CODES, TRADE_WORDS, PAYMENT_TERMS,
    VENDOR_CATEGORIES, CLIENT_CATEGORIES,
)

_used_names = set()


def _generate_address(city):
    number = random.randint(100, 19999)
    street = random.choice(STREET_NAMES)
    addr = f"{number} {street}"
    if random.random() < 0.30:
        addr += f", {random.choice(SUITE_TYPES)} {random.randint(1, 400)}"
    return addr


def _get_zip(city):
    return random.choice(ZIP_CODES.get(city, ["78701"]))


def _generate_business_name(category_label):
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    loc = random.choice(LOCATION_DESCRIPTORS)
    suffix = random.choice(BUSINESS_SUFFIXES)

    trade = None
    for key, words in TRADE_WORDS.items():
        if key.lower() in category_label.lower():
            if words:
                trade = random.choice(words)
            break
    if trade is None:
        trade = category_label.split()[0]

    if "Homeowner" in category_label:
        patterns = [
            f"{first} {last}",
            f"{first} & {random.choice(FIRST_NAMES)} {last}",
            f"The {last} Family",
        ]
    else:
        patterns = [
            f"{first}'s {trade}", f"{last} {trade} {suffix}",
            f"{first} {last} {trade}", f"{loc} {trade} {suffix}",
            f"{loc} {trade}", f"{trade} {suffix}",
            f"All Pro {trade}", f"Premier {trade} {suffix}",
            f"Reliable {trade}", f"{trade} Depot",
            f"{first[0]}&{last[0]} {trade}", f"{loc[:3].upper()} {trade}",
        ]

    random.shuffle(patterns)
    for name in patterns:
        if name not in _used_names:
            _used_names.add(name)
            return name
    name = f"{patterns[0]} {random.randint(2, 9)}"
    _used_names.add(name)
    return name


def _generate_contact():
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    return first, last


def _generate_ein():
    prefix = random.choice([74, 75, 76, 82, 83, 84, 46, 47])
    return f"{prefix}-{random.randint(1000000, 9999999)}"


def _generate_email(first, last, biz_name):
    slug = biz_name.lower().replace(" ", "").replace("&", "").replace("'", "")[:12]
    return random.choice([
        f"{first.lower()}@{slug}.com",
        f"{first.lower()}.{last.lower()}@{slug}.com",
        f"{first[0].lower()}{last.lower()}@{slug}.com",
        f"info@{slug}.com",
    ])


def _generate_website(biz_name):
    slug = biz_name.lower().replace(" ", "").replace("&", "").replace("'", "")[:18]
    return f"www.{slug}.com"


def _hub_likelihood(category_label):
    if any(kw in category_label for kw in ["Supply", "Material", "Rental", "Hardware", "Depot"]):
        return "high"
    if any(kw in category_label for kw in ["Contractor", "Insurance", "Waste"]):
        return "medium"
    return "low"


def _txn_size_and_volume(category_label):
    if "Supply" in category_label or "Material" in category_label:
        avg = random.randint(500, 15000)
        return avg, avg * random.randint(12, 60)
    if "Contractor" in category_label or "Construction" in category_label:
        avg = random.randint(2000, 50000)
        return avg, avg * random.randint(4, 20)
    if "Rental" in category_label:
        avg = random.randint(300, 5000)
        return avg, avg * random.randint(10, 40)
    if "Homeowner" in category_label:
        avg = random.randint(5000, 80000)
        return avg, avg
    if "Insurance" in category_label or "Accounting" in category_label:
        avg = random.randint(500, 5000)
        return avg, avg * random.randint(4, 12)
    if "Property Management" in category_label or "HOA" in category_label:
        avg = random.randint(1000, 15000)
        return avg, avg * random.randint(6, 24)
    avg = random.randint(1000, 25000)
    return avg, avg * random.randint(4, 15)


def _payment_terms(category_label):
    if "Homeowner" in category_label:
        return random.choice(["due_on_receipt", "due_on_receipt", "net_15"])
    if "Supply" in category_label or "Material" in category_label:
        return random.choice(["net_30", "net_30", "net_60", "net_15"])
    if "Contractor" in category_label:
        return random.choice(["net_30", "net_15", "due_on_receipt"])
    return random.choice(PAYMENT_TERMS)


def generate_pool(categories, prefix, pool_size):
    """Generate a ground truth pool of businesses."""
    _used_names.clear()
    pool = []
    serial = 1

    for (cat_label, naics, count, commodities, cities) in categories:
        for _ in range(count):
            if serial > pool_size:
                break

            city = random.choice(cities)
            name = _generate_business_name(cat_label)
            c_first, c_last = _generate_contact()
            avg_txn, annual_vol = _txn_size_and_volume(cat_label)

            has_addr = random.random() < 0.75

            if "Homeowner" in cat_label:
                legal = "Individual"
            elif random.random() < 0.45:
                legal = "LLC"
            elif random.random() < 0.65:
                legal = "Sole Proprietorship"
            elif random.random() < 0.85:
                legal = "Corporation"
            else:
                legal = "Partnership"

            entry = {
                "serial_id": f"{prefix}-{serial:03d}",
                # Identity
                "canonical_name": name,
                "ein": _generate_ein() if random.random() < 0.65 else None,
                "contact_name": f"{c_first} {c_last}" if random.random() < 0.80 else None,
                "email": _generate_email(c_first, c_last, name) if random.random() < 0.60 else None,
                "phone": f"512-{random.randint(200,999)}-{random.randint(1000,9999)}" if random.random() < 0.70 else None,
                # Industry
                "category": cat_label,
                "naics": naics,
                "commodities": random.sample(commodities, min(len(commodities), random.randint(1, 3))),
                # Location
                "street_address": _generate_address(city) if has_addr else None,
                "city": city,
                "state": "TX",
                "zip": _get_zip(city) if has_addr else None,
                # Behavioral
                "website": _generate_website(name) if random.random() < 0.40 else None,
                "expected_annual_volume": annual_vol if random.random() < 0.55 else None,
                "payment_terms": _payment_terms(cat_label) if random.random() < 0.50 else None,
                # Metadata
                "legal_structure": legal,
                "avg_transaction_size": avg_txn,
                "hub_likelihood": _hub_likelihood(cat_label),
            }
            pool.append(entry)
            serial += 1

        if serial > pool_size:
            break

    return pool


def generate_vendor_pool():
    return generate_pool(VENDOR_CATEGORIES, "V", cfg.VENDOR_POOL_SIZE)


def generate_client_pool():
    return generate_pool(CLIENT_CATEGORIES, "C", cfg.CLIENT_POOL_SIZE)
