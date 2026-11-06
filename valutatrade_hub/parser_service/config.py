"""Configuration for the Parser Service."""

import os
from pathlib import Path

from valutatrade_hub.core.currencies import (
    CRYPTO_CURRENCY_CODES,
    FIAT_CURRENCY_CODES,
    SUPPORTED_CURRENCY_CODES,
)
from valutatrade_hub.infra.settings import SettingsLoader

# Project settings
_settings = SettingsLoader()

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_path(path: str | Path) -> Path:
    """Resolve a data path relative to the project root."""
    directory = Path(path)

    if directory.is_absolute():
        return directory

    return PROJECT_ROOT / directory


# Data storage
DATA_DIR = _resolve_path(_settings.get("data_dir", "data"))
RATES_FILE = DATA_DIR / "rates.json"
EXCHANGE_RATES_FILE = DATA_DIR / "exchange_rates.json"


# Currency settings
BASE_CURRENCY = str(_settings.get("base_currency", "USD")).upper()

SUPPORTED_FIAT_CURRENCIES = tuple(FIAT_CURRENCY_CODES)
SUPPORTED_CRYPTO_CURRENCIES = tuple(CRYPTO_CURRENCY_CODES)
SUPPORTED_CURRENCIES = tuple(SUPPORTED_CURRENCY_CODES)

CRYPTO_ID_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "LTC": "litecoin",
}


# API settings
COINGECKO_BASE_URL = os.getenv(
    "COINGECKO_BASE_URL",
    "https://api.coingecko.com/api/v3",
).rstrip("/")

EXCHANGE_RATE_API_BASE_URL = os.getenv(
    "EXCHANGE_RATE_API_BASE_URL",
    "https://v6.exchangerate-api.com/v6",
).rstrip("/")

EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY")


# Request and cache settings
API_TIMEOUT_SECONDS = float(_settings.get("api_timeout", 10))

RATES_TTL_SECONDS = int(_settings.get("rates_ttl_seconds", 3600))


# Configuration validation
if BASE_CURRENCY not in SUPPORTED_CURRENCIES:
    raise ValueError(f"Unsupported base currency: {BASE_CURRENCY}")

if API_TIMEOUT_SECONDS <= 0:
    raise ValueError("API timeout must be positive.")

if RATES_TTL_SECONDS < 0:
    raise ValueError("Rates TTL cannot be negative.")

if set(CRYPTO_ID_MAP) != set(SUPPORTED_CRYPTO_CURRENCIES):
    raise ValueError("CRYPTO_ID_MAP must contain all supported cryptocurrencies.")
