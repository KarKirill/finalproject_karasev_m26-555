"""Необязательный планировщик периодического обновления курсов."""

import logging
from threading import Event, RLock, Thread, current_thread
from typing import Any

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.updater import RatesUpdater

logger = logging.getLogger(__name__)


class RatesScheduler:
    """Периодически обновляет валютные курсы в фоновом потоке."""

    def __init__(
        self,
        updater: RatesUpdater | None = None,
        interval_seconds: int | None = None,
    ) -> None:
        """Настроить сервис обновления и интервал проверки."""
        if interval_seconds is None:
            interval_seconds = SettingsLoader().get(
                "scheduler_interval_seconds",
                60,
            )

        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, int)
            or interval_seconds <= 0
        ):
            raise ValueError(
                "Интервал обновления должен быть положительным целым числом."
            )

        self.updater = updater if updater is not None else RatesUpdater()
        self.interval_seconds = interval_seconds

        self._stop_event = Event()
        self._thread: Thread | None = None
        self._thread_lock = RLock()

    def run_once(self) -> dict[str, Any]:
        """Однократно обновить курсы валют."""
        logger.debug("Запущено обновление курсов.")
        return self.updater.run_update()

    def run_forever(self, stop_event: Event | None = None) -> None:
        """Обновлять курсы периодически до получения сигнала остановки."""
        event = stop_event if stop_event is not None else self._stop_event

        logger.info(
            "Планировщик запущен. Интервал обновления: %d секунд.",
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
            except Exception:
                logger.exception("Непредвиденная ошибка при обновлении курсов.")

            event.wait(self.interval_seconds)

        logger.info("Планировщик остановлен.")

    def start(self) -> None:
        """Запустить планировщик в фоновом потоке."""
        with self._thread_lock:
            if self._thread is not None and self._thread.is_alive():
                logger.warning("Планировщик уже запущен.")
                return

            self._stop_event.clear()

            self._thread = Thread(
                target=self.run_forever,
                name="rates-scheduler",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Остановить планировщик и дождаться завершения потока."""
        self._stop_event.set()

        with self._thread_lock:
            thread = self._thread

        if thread is not None and thread is not current_thread():
            thread.join()

        with self._thread_lock:
            if self._thread is thread:
                self._thread = None
