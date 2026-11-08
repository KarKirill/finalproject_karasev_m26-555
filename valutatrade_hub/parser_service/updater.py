"""Сервис обновления курсов валют."""

import logging
import math
from datetime import datetime, timezone
from typing import Any

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import (
    BASE_CURRENCY,
    RATES_TTL_SECONDS,
    SUPPORTED_CURRENCIES,
)
from valutatrade_hub.parser_service.storage import RatesStorage

logger = logging.getLogger(__name__)


class RatesUpdater:
    """Получает, обновляет и кеширует курсы валют."""

    def __init__(
        self,
        crypto_client: BaseApiClient | None = None,
        fiat_client: BaseApiClient | None = None,
        storage: RatesStorage | None = None,
        ttl_seconds: int = RATES_TTL_SECONDS,
    ) -> None:
        """Инициализировать сервис обновления курсов."""
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or ttl_seconds < 0
        ):
            raise ValueError(
                "Время актуальности курсов должно быть неотрицательным целым числом."
            )

        self.crypto_client = (
            crypto_client if crypto_client is not None else CoinGeckoClient()
        )
        self.fiat_client = (
            fiat_client if fiat_client is not None else ExchangeRateApiClient()
        )
        self.storage = storage if storage is not None else RatesStorage()
        self.ttl_seconds = ttl_seconds

    def _is_cache_fresh(self, snapshot: dict[str, Any]) -> bool:
        """Проверить актуальность всех сохранённых курсов."""
        pairs = snapshot.get("pairs")

        if not isinstance(pairs, dict):
            return False

        required_pairs = [
            f"{code}_{BASE_CURRENCY}"
            for code in SUPPORTED_CURRENCIES
            if code != BASE_CURRENCY
        ]

        if not required_pairs:
            return False

        current_time = datetime.now(timezone.utc)

        for pair in required_pairs:
            rate_data = pairs.get(pair)

            if not isinstance(rate_data, dict):
                return False

            rate = rate_data.get("rate")

            if (
                isinstance(rate, bool)
                or not isinstance(rate, (int, float))
                or not math.isfinite(rate)
                or rate <= 0
            ):
                return False

            updated_at = rate_data.get("updated_at")

            if not isinstance(updated_at, str):
                return False

            try:
                timestamp = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            except ValueError:
                return False

            if timestamp.tzinfo is None:
                return False

            age = (current_time - timestamp.astimezone(timezone.utc)).total_seconds()

            if age < 0 or age > self.ttl_seconds:
                return False

        return True

    def get_rates(
        self,
        force_update: bool = False,
    ) -> dict[str, Any]:
        """Получить актуальные курсы с учётом времени кеширования."""
        snapshot = self.storage.load_rates()

        if not force_update and self._is_cache_fresh(snapshot):
            logger.debug("Используется актуальный кеш курсов.")
            return snapshot

        logger.info("Кеш курсов устарел или отсутствует.")

        return self.update_rates()

    def _fetch_and_store_rates(
        self,
        selected_source: str | None = None,
    ) -> tuple[dict[str, Any], int, dict[str, str]]:
        """Получить курсы от API и сохранить их в хранилище."""
        updated_at = (
            datetime.now(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )

        clients = (
            ("CoinGecko", self.crypto_client),
            ("ExchangeRate-API", self.fiat_client),
        )

        if selected_source == "coingecko":
            clients = clients[:1]
        elif selected_source == "exchangerate":
            clients = clients[1:]

        updated_count = 0
        failures = {}

        for source, client in clients:
            try:
                rates = client.fetch_rates()
            except ApiRequestError as error:
                failures[source] = error.reason

                logger.warning(
                    "Не удалось получить курсы от %s: %s",
                    source,
                    error.reason,
                )
                continue

            if not rates:
                failures[source] = "Источник не вернул ни одного курса."

                logger.warning(
                    "%s не вернул ни одного курса.",
                    source,
                )
                continue

            self.storage.save_rates(
                rates,
                source,
                updated_at,
            )

            updated_count += len(rates)

            logger.info(
                "Получено и сохранено курсов от %s: %d",
                source,
                len(rates),
            )

        snapshot = self.storage.load_rates()

        return snapshot, updated_count, failures

    def run_update(self, source: str | None = None) -> dict[str, Any]:
        """Обновить курсы выбранного источника или всех источников."""
        if source not in (None, "coingecko", "exchangerate"):
            raise ValueError(
                "Неизвестный источник курсов. "
                "Допустимые значения: coingecko, exchangerate."
            )

        logger.info(
            "Запуск обновления курсов. Источник: %s",
            source or "все",
        )

        snapshot, updated_count, failures = self._fetch_and_store_rates(source)

        if updated_count == 0:
            details = "; ".join(
                f"{source}: {reason}" for source, reason in failures.items()
            )

            logger.error(
                "Не удалось обновить курсы ни из одного источника: %s",
                details,
            )

            raise ApiRequestError(
                f"Не удалось обновить курсы ни из одного источника. {details}"
            )

        if failures:
            logger.warning(
                "Обновление курсов выполнено частично. Ошибки: %s",
                failures,
            )

        logger.info(
            "Обновление завершено. Обновлено курсов: %d",
            updated_count,
        )

        return {
            "updated_count": updated_count,
            "last_refresh": snapshot.get("last_refresh"),
            "errors": failures,
        }

    def update_rates(self) -> dict[str, Any]:
        """Обновить курсы и вернуть актуальный снимок."""
        self.run_update()
        return self.storage.load_rates()
