"""Конфигурация сервиса Parser Service."""

import os
from pathlib import Path

from valutatrade_hub.core.currencies import (
    CRYPTO_CURRENCY_CODES,
    FIAT_CURRENCY_CODES,
    SUPPORTED_CURRENCY_CODES,
)
from valutatrade_hub.infra.settings import SettingsLoader

# Загрузка настроек проекта
_settings = SettingsLoader()

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_path(path: str | Path) -> Path:
    """Определить абсолютный путь относительно корня проекта."""
    directory = Path(path)

    if directory.is_absolute():
        return directory

    return PROJECT_ROOT / directory


# Настройки хранения данных
DATA_DIR = _resolve_path(_settings.get("data_dir", "data"))
RATES_FILE = DATA_DIR / "rates.json"
EXCHANGE_RATES_FILE = DATA_DIR / "exchange_rates.json"


# Настройки валют
BASE_CURRENCY = str(_settings.get("base_currency", "USD")).upper()

SUPPORTED_FIAT_CURRENCIES = tuple(FIAT_CURRENCY_CODES)
SUPPORTED_CRYPTO_CURRENCIES = tuple(CRYPTO_CURRENCY_CODES)
SUPPORTED_CURRENCIES = tuple(SUPPORTED_CURRENCY_CODES)

CRYPTO_ID_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "LTC": "litecoin",
}


# Настройки внешних API
COINGECKO_BASE_URL = os.getenv(
    "COINGECKO_BASE_URL",
    "https://api.coingecko.com/api/v3",
).rstrip("/")

EXCHANGE_RATE_API_BASE_URL = os.getenv(
    "EXCHANGE_RATE_API_BASE_URL",
    "https://v6.exchangerate-api.com/v6",
).rstrip("/")

EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY")


# Настройки запросов и кеширования
API_TIMEOUT_SECONDS = float(_settings.get("api_timeout", 10))

RATES_TTL_SECONDS = int(_settings.get("rates_ttl_seconds", 3600))


# Проверка корректности конфигурации
if BASE_CURRENCY not in SUPPORTED_CURRENCIES:
    raise ValueError(f"Неподдерживаемая базовая валюта: {BASE_CURRENCY}")

if API_TIMEOUT_SECONDS <= 0:
    raise ValueError("Время ожидания API-запроса должно быть положительным.")

if RATES_TTL_SECONDS < 0:
    raise ValueError("Время актуальности курсов не может быть отрицательным.")

if set(CRYPTO_ID_MAP) != set(SUPPORTED_CRYPTO_CURRENCIES):
    raise ValueError("CRYPTO_ID_MAP должен содержать все поддерживаемые криптовалюты.")
