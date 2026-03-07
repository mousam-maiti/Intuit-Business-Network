"""
Bucket key generation — design doc §2.1 find_candidates implementation.

Generates bucket keys from persona dimensions for candidate lookup.
Each key maps to a Redis sorted set of golden_record_ids.
"""
from __future__ import annotations
from models.persona import ClassifiedPersona


def generate_bucket_keys(persona: ClassifiedPersona, max_commodity_kw: int = 3) -> list[str]:
    """Generate all bucket keys from a classified persona.

    Bucket key format matches design doc:
      Identity:   name:{TOKEN}+{STATE}     "name:BOBS+TX"
                  ein:{EIN}                 "ein:74-8841234"
                  phone:{DIGITS}            "phone:5124551234"
                  email_domain:{DOMAIN}     "email_domain:bobsplumbing.com"
      Industry:   naics4:{CODE4}+{STATE}    "naics4:2382+TX"
                  naics3:{CODE3}+{STATE}    "naics3:238+TX"
      Location:   zip3:{ZIP3}               "zip3:787"
                  city:{CITY}+{STATE}       "city:AUSTIN+TX"
      Commodity:  commodity:{KW}+{STATE}    "commodity:pvc pipe+TX"
    """
    keys: list[str] = []
    ident = persona.identity
    ind = persona.industry
    loc = persona.location
    comm = persona.commodity
    state = loc.state.upper() if loc.state else None

    # ── Identity buckets ────────────────────────────────────
    if ident.name_first_token and state:
        keys.append(f"name:{ident.name_first_token.upper()}+{state}")

    if ident.ein_clean:
        keys.append(f"ein:{ident.ein_clean}")

    if ident.phone_digits:
        keys.append(f"phone:{ident.phone_digits}")

    if ident.email_domain:
        keys.append(f"email_domain:{ident.email_domain.lower()}")

    # ── Industry buckets ────────────────────────────────────
    if ind.naics_subsector and state:
        keys.append(f"naics3:{ind.naics_subsector}+{state}")

    if ind.naics_code and state and len(ind.naics_code) >= 4:
        code4 = ind.naics_code[:4]
        keys.append(f"naics4:{code4}+{state}")

    # ── Location buckets ────────────────────────────────────
    if loc.zip3:
        keys.append(f"zip3:{loc.zip3}")

    if loc.city_norm and state:
        keys.append(f"city:{loc.city_norm.upper()}+{state}")

    # ── Commodity buckets ───────────────────────────────────
    if comm.top_keywords and state:
        for kw in comm.top_keywords[:max_commodity_kw]:
            keys.append(f"commodity:{kw.lower()}+{state}")

    return keys
