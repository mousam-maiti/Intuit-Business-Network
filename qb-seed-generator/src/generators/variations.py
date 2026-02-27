"""Generate realistic display name variations for the same business.

This is the core of what makes entity resolution necessary.
"Bob's Plumbing LLC" in Acme's books becomes "Bobs Plumbing" in BuildRight's books.
"""

import random
import re


def _drop_apostrophe(name):
    """Bob's → Bobs"""
    return name.replace("'", "")


def _drop_suffix(name):
    """Williams Concrete & Co → Williams Concrete"""
    suffixes = [
        " LLC", " Inc", " Corp", " Co", " & Co", " & Sons",
        " Services", " Solutions", " Supply", " Enterprises",
        " Group", " Pro", " Plus", " Express", " Specialists",
        " Experts", " Team", " Works", " Masters", " Direct",
    ]
    for s in suffixes:
        if name.endswith(s):
            return name[: -len(s)]
    return name


def _swap_suffix(name):
    """Williams Concrete LLC → Williams Concrete Inc"""
    pairs = {
        " LLC": [" Inc", " Co"],
        " Inc": [" LLC", " Corp"],
        " Corp": [" Inc", " LLC"],
        " Co": [" LLC", " Inc"],
    }
    for old, options in pairs.items():
        if name.endswith(old):
            return name[: -len(old)] + random.choice(options)
    return name


def _abbreviate_first_name(name):
    """Bob's Plumbing → B's Plumbing, Robert Chen → R. Chen"""
    parts = name.split()
    if len(parts) >= 2:
        if "'" in parts[0]:
            # Bob's → B's
            return parts[0][0] + "'s " + " ".join(parts[1:])
        else:
            return parts[0][0] + ". " + " ".join(parts[1:])
    return name


def _use_initials(name):
    """Bob's Plumbing Supply → BPS, Hill Country Homes → HCH"""
    words = re.findall(r'[A-Z][a-z]*', name)
    if len(words) >= 2:
        initials = "".join(w[0] for w in words)
        # Sometimes add the trade word back
        if random.random() < 0.5 and len(words) >= 2:
            return initials + " " + words[-1]
        return initials
    return name


def _add_location(name, city):
    """Bob's Plumbing → Bob's Plumbing Austin"""
    return f"{name} {city}"


def _drop_location(name):
    """Austin Lumber Supply → Lumber Supply"""
    locations = [
        "Austin", "Round Rock", "Cedar Park", "ATX", "Central Texas",
        "Hill Country", "Lone Star", "Capital City", "Travis County",
        "Greater Austin", "South Austin", "North Austin", "East Austin",
        "Lakeway", "Texas", "TX",
    ]
    for loc in locations:
        if name.startswith(loc + " "):
            return name[len(loc) + 1:]
    return name


def _typo(name):
    """Introduce a realistic typo — doubled letter, dropped letter, swap"""
    if len(name) < 4:
        return name
    i = random.randint(1, len(name) - 2)
    r = random.random()
    if r < 0.33:
        # Drop a letter
        return name[:i] + name[i + 1:]
    elif r < 0.66:
        # Double a letter
        return name[:i] + name[i] + name[i:]
    else:
        # Swap adjacent
        return name[:i] + name[i + 1] + name[i] + name[i + 2:]


def _add_the(name):
    """Plumbing Depot → The Plumbing Depot"""
    if not name.startswith("The "):
        return "The " + name
    return name


def _period_in_suffix(name):
    """LLC → L.L.C., Inc → Inc."""
    replacements = {
        " LLC": [" L.L.C.", " Llc"],
        " Inc": [" Inc.", " INC"],
    }
    for old, options in replacements.items():
        if name.endswith(old):
            return name[: -len(old)] + random.choice(options)
    return name


# All variation functions, grouped by severity
MILD_VARIATIONS = [
    _drop_apostrophe,
    _period_in_suffix,
    _add_the,
]

MODERATE_VARIATIONS = [
    _drop_suffix,
    _swap_suffix,
    _abbreviate_first_name,
]

AGGRESSIVE_VARIATIONS = [
    _use_initials,
    _typo,
]

LOCATION_VARIATIONS = [
    _drop_location,
]


def generate_variation(canonical_name, city=None):
    """Generate a realistic display name variation.

    Returns a name that a different QB user might type for the same business.
    """
    # Pick severity: 50% mild, 30% moderate, 15% aggressive, 5% location-based
    r = random.random()
    if r < 0.50:
        fn = random.choice(MILD_VARIATIONS)
        result = fn(canonical_name)
    elif r < 0.80:
        fn = random.choice(MODERATE_VARIATIONS)
        result = fn(canonical_name)
    elif r < 0.95:
        fn = random.choice(AGGRESSIVE_VARIATIONS)
        result = fn(canonical_name)
    else:
        # Location-based: either add or drop location
        if city and random.random() < 0.5:
            result = _add_location(_drop_suffix(canonical_name), city)
        else:
            result = _drop_location(canonical_name)

    # 20% chance of stacking a second mild variation
    if random.random() < 0.20 and result != canonical_name:
        fn2 = random.choice(MILD_VARIATIONS)
        result = fn2(result)

    # If no change happened, apply a guaranteed mild one
    if result == canonical_name:
        result = _drop_apostrophe(canonical_name)
    if result == canonical_name:
        result = _drop_suffix(canonical_name)
    if result == canonical_name:
        result = canonical_name + " " + random.choice(["LLC", "Inc", "Co"])

    return result
