
"""Необязательный планировщик периодического обновления курсов."""

import logging
from threading import Event
from typing import Any

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.updater import RatesUpdater


logger = logging.getLogger(__name__)


class RatesScheduler:
    """Периодически проверяет актуальность валютных курсов."""

    def __init__(
        self,
        updater: RatesUpdater | None = None,
        interval_seconds: int = 60,
    ) -> None:
        """Настроить сервис обновления и интервал проверки."""
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, int)
            or interval_seconds <= 0
        ):
            raise ValueError(
                "Интервал проверки должен быть положительным целым числом."
            )

        self.updater = updater if updater is not None else RatesUpdater()
        self.interval_seconds = interval_seconds

    def run_once(self) -> dict[str, Any]:
        """Однократно проверить актуальность и обновить курсы при необходимости."""
        logger.debug("Запущена проверка актуальности курсов.")
        return self.updater.get_rates()

    def run_forever(self, stop_event: Event | None = None) -> None:
        """Проверять курсы периодически до получения сигнала остановки."""
        event = stop_event if stop_event is not None else Event()

        logger.info(
            "Планировщик запущен. Интервал проверки: %d секунд.",
            self.interval_seconds,
        )

        while not event.is_set():
            try:
                self.run_once()
            except ApiRequestError as error:
                logger.warning(
                    "Не удалось обновить курсы: %s",
                    error.reason,
                )

            event.wait(self.interval_seconds)

        logger.info("Планировщик остановлен.")
