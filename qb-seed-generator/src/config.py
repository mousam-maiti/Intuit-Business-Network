"""Centralized configuration from .env file."""

import os
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_root = Path(__file__).resolve().parent.parent
load_dotenv(_root / ".env")


def _int(key, default):
    return int(os.getenv(key, default))


def _float(key, default):
    return float(os.getenv(key, default))


def _str(key, default):
    return os.getenv(key, default)


def _date(key, default):
    return date.fromisoformat(os.getenv(key, default))


def _parse_company_targets(raw):
    """Parse COMPANY_TARGETS env var into {company_id: (vendor_count, customer_count)}.

    Format: "1:24:12,2:20:10,3:16:8"
    Returns None when not set (falls back to random-range behavior).
    """
    if not raw:
        return None
    targets = {}
    for part in raw.split(","):
        cid, v, c = part.strip().split(":")
        targets[int(cid)] = (int(v), int(c))
    return targets


class Config:
    """All generation parameters — override via .env"""

    # Pool sizes
    VENDOR_POOL_SIZE = _int("VENDOR_POOL_SIZE", 100)
    CLIENT_POOL_SIZE = _int("CLIENT_POOL_SIZE", 100)

    # QB accounts
    QB_ACCOUNT_COUNT = _int("QB_ACCOUNT_COUNT", 10)

    # Per-company exact targets (overrides random assignment ranges)
    COMPANY_TARGETS = _parse_company_targets(os.getenv("COMPANY_TARGETS"))

    # Assignment ranges
    VENDORS_PER_ACCOUNT_MIN = _int("VENDORS_PER_ACCOUNT_MIN", 15)
    VENDORS_PER_ACCOUNT_MAX = _int("VENDORS_PER_ACCOUNT_MAX", 40)
    CLIENTS_PER_ACCOUNT_MIN = _int("CLIENTS_PER_ACCOUNT_MIN", 10)
    CLIENTS_PER_ACCOUNT_MAX = _int("CLIENTS_PER_ACCOUNT_MAX", 30)

    # Hub overlap
    HUB_HIGH_MIN = _int("HUB_HIGH_MIN_ACCOUNTS", 5)
    HUB_HIGH_MAX = _int("HUB_HIGH_MAX_ACCOUNTS", 8)
    HUB_MEDIUM_MIN = _int("HUB_MEDIUM_MIN_ACCOUNTS", 2)
    HUB_MEDIUM_MAX = _int("HUB_MEDIUM_MAX_ACCOUNTS", 4)
    HUB_LOW_MIN = _int("HUB_LOW_MIN_ACCOUNTS", 1)
    HUB_LOW_MAX = _int("HUB_LOW_MAX_ACCOUNTS", 2)

    # Name variation
    NAME_VARIATION_PROB = _float("NAME_VARIATION_PROBABILITY", 0.60)

    # Field fill rates (per-account sparsity on top of pool sparsity)
    FILL_RATES = {
        "ein":              _float("FIELD_EIN_FILL_RATE", 0.40),
        "contact_name":     _float("FIELD_CONTACT_FILL_RATE", 0.55),
        "email":            _float("FIELD_EMAIL_FILL_RATE", 0.35),
        "phone":            _float("FIELD_PHONE_FILL_RATE", 0.50),
        "street_address":   _float("FIELD_ADDRESS_FILL_RATE", 0.45),
        "category":         _float("FIELD_CATEGORY_FILL_RATE", 0.60),
        "commodity":        _float("FIELD_COMMODITY_FILL_RATE", 0.30),
        "website":          _float("FIELD_WEBSITE_FILL_RATE", 0.15),
        "expected_volume":  _float("FIELD_VOLUME_FILL_RATE", 0.20),
        "payment_terms":    _float("FIELD_TERMS_FILL_RATE", 0.25),
    }

    # Transactions
    TXN_START = _date("TRANSACTION_START_DATE", "2023-01-01")
    TXN_END = _date("TRANSACTION_END_DATE", "2025-02-01")
    TXN_PER_REL_MIN = _int("TRANSACTIONS_PER_REL_MIN", 3)
    TXN_PER_REL_MAX = _int("TRANSACTIONS_PER_REL_MAX", 40)

    # MySQL
    MYSQL_HOST = _str("MYSQL_HOST", "localhost")
    MYSQL_PORT = _int("MYSQL_PORT", 3306)
    MYSQL_DATABASE = _str("MYSQL_DATABASE", "quickbooks")
    MYSQL_USER = _str("MYSQL_USER", "qb_admin")
    MYSQL_PASSWORD = _str("MYSQL_PASSWORD", "qb_admin_pass")

    # Output
    SEED_DIR = _root / _str("SEED_OUTPUT_DIR", "seed")
    RANDOM_SEED = _int("RANDOM_SEED", 42)


cfg = Config()
