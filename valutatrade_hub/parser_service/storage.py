"""Хранилище актуальных курсов и истории валютных операций."""

import math
from datetime import datetime, timezone
from typing import Any

from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.parser_service.config import (
    BASE_CURRENCY,
    SUPPORTED_CURRENCIES,
)


class RatesStorage:
    """Управляет кешем актуальных курсов и историей их обновлений."""

    def __init__(
        self,
        database: DatabaseManager | None = None,
    ) -> None:
        """Инициализировать хранилище курсов."""
        self.database = database if database is not None else DatabaseManager()

    @staticmethod
    def _get_timestamp(updated_at: str | None = None) -> str:
        """Получить время обновления в формате UTC."""
        if updated_at is None:
            current_time = datetime.now(timezone.utc)
        else:
            try:
                current_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError("Некорректный формат времени обновления.") from error

            if current_time.tzinfo is None:
                raise ValueError("Время обновления должно содержать часовой пояс.")

            current_time = current_time.astimezone(timezone.utc)

        return current_time.isoformat(timespec="microseconds").replace("+00:00", "Z")

    @staticmethod
    def _validate_rate(pair: str, rate: float) -> None:
        """Проверить валютную пару и значение её курса."""
        parts = pair.split("_")

        if (
            len(parts) != 2
            or parts[0] not in SUPPORTED_CURRENCIES
            or parts[0] == BASE_CURRENCY
            or parts[1] != BASE_CURRENCY
        ):
            raise ValueError(f"Некорректная валютная пара: {pair}.")

        if (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float))
            or not math.isfinite(rate)
            or rate <= 0
        ):
            raise ValueError(f"Некорректное значение курса для пары {pair}.")

    def load_rates(self) -> dict[str, Any]:
        """Загрузить актуальный снимок курсов."""
        rates = self.database.load_rates()

        if not isinstance(rates, dict) or not isinstance(rates.get("pairs"), dict):
            raise ValueError("Файл актуальных курсов имеет некорректную структуру.")

        return rates

    def load_history(self) -> list[dict[str, Any]]:
        """Загрузить историю изменений курсов."""
        history = self.database.load_exchange_rates()

        if not isinstance(history, list):
            raise ValueError("Файл истории курсов имеет некорректную структуру.")

        return history

    def save_rates(
        self,
        rates: dict[str, float],
        source: str,
        updated_at: str | None = None,
    ) -> dict[str, Any]:
        """Обновить кеш курсов и добавить записи в историю."""
        if not isinstance(rates, dict) or not rates:
            raise ValueError("Необходимо передать хотя бы один валютный курс.")

        if not isinstance(source, str) or not source.strip():
            raise ValueError("Источник курсов должен быть указан.")

        timestamp = self._get_timestamp(updated_at)

        validated_rates = {}

        for pair, rate in rates.items():
            self._validate_rate(pair, rate)
            validated_rates[pair] = float(rate)

        # Обновляем актуальный снимок, сохраняя старые курсы,
        # которые не были получены от источников в этом обновлении.
        def update_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
            if not isinstance(snapshot, dict):
                raise ValueError("Некорректная структура актуального кеша.")

            pairs = snapshot.get("pairs", {})

            if not isinstance(pairs, dict):
                raise ValueError("Раздел валютных пар имеет некорректную структуру.")

            updated_pairs = dict(pairs)

            for pair, rate in validated_rates.items():
                updated_pairs[pair] = {
                    "rate": rate,
                    "updated_at": timestamp,
                    "source": source,
                }

            return {
                "pairs": updated_pairs,
                "last_refresh": timestamp,
            }

        snapshot = self.database.update_json(
            "rates",
            update_snapshot,
            default={"pairs": {}, "last_refresh": None},
        )

        # Добавляем новые записи в историю без дублирования ID.
        def update_history(
            history: list[dict[str, Any]],
        ) -> list[dict[str, Any]]:
            if not isinstance(history, list):
                raise ValueError("Некорректная структура истории курсов.")

            updated_history = list(history)

            existing_ids = {
                record.get("id") for record in history if isinstance(record, dict)
            }

            history_timestamp = (
                timestamp.replace("-", "").replace(":", "").replace(".", "")
            )

            for pair, rate in validated_rates.items():
                record_id = f"{pair}_{history_timestamp}"

                if record_id in existing_ids:
                    continue

                updated_history.append(
                    {
                        "id": record_id,
                        "pair": pair,
                        "rate": rate,
                        "updated_at": timestamp,
                        "source": source,
                    }
                )

                existing_ids.add(record_id)

            return updated_history

        self.database.update_json(
            "exchange_rates",
            update_history,
            default=[],
        )

        return snapshot
