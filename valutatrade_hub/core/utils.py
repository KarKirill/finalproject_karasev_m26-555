from collections.abc import Mapping
from math import isfinite
from typing import Any

# Фиксированные курсы для работы без Parser Service.
# Значения показывают стоимость одной единицы валюты в USD.
EXCHANGE_RATES = {
    "USD": 1.0,
    "EUR": 1.0786,
    "BTC": 59337.21,
    "ETH": 3720.0,
    "RUB": 0.01016,
}


def get_usd_rate(
    currency_code: str,
    rates: Mapping[str, Any] | None = None,
) -> float:
    """Возвращает стоимость одной единицы валюты в USD."""
    if not isinstance(currency_code, str) or not currency_code.strip():
        raise ValueError("Код валюты не может быть пустым.")

    code = currency_code.strip().upper()

    if code == "USD":
        return 1.0

    source = EXCHANGE_RATES if rates is None else rates
    pairs = source.get("pairs", source)

    if not isinstance(pairs, Mapping):
        raise ValueError("Некорректный формат данных о курсах.")

    rate_data = pairs.get(f"{code}_USD")

    if rate_data is None:
        rate_data = pairs.get(code)

    if isinstance(rate_data, Mapping):
        rate_data = rate_data.get("rate")

    if (
        isinstance(rate_data, bool)
        or not isinstance(rate_data, (int, float))
        or not isfinite(rate_data)
        or rate_data <= 0
    ):
        raise ValueError(f"Не удалось получить курс {code} к USD.")

    return float(rate_data)
