"""Настройка файлового и консольного логирования приложения."""

import logging
import sys
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterator

from valutatrade_hub.infra.settings import SettingsLoader

PROJECT_ROOT = Path(__file__).resolve().parents[1]

APP_LOGGER_NAME = "valutatrade_hub"
PARSER_LOGGER_NAME = "valutatrade_hub.parser_service"


def _resolve_log_path(value: str) -> Path:
    """Получить абсолютный путь к файлу журнала."""
    path = Path(value)

    if path.is_absolute():
        return path

    return PROJECT_ROOT / path


def _add_file_handler(
    logger: logging.Logger,
    path: Path,
    level: int,
    formatter: logging.Formatter,
) -> None:
    """Добавить файловый обработчик без дублирования."""
    for handler in logger.handlers:
        if (
            isinstance(handler, logging.FileHandler)
            and Path(handler.baseFilename) == path
        ):
            handler.setLevel(level)
            handler.setFormatter(formatter)
            return

    path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        filename=path,
        maxBytes=1_048_576,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(formatter)

    logger.addHandler(handler)


def setup_logging() -> None:
    """Настроить журналы действий и сервиса обновления курсов."""
    settings = SettingsLoader()

    log_dir = settings.get("log_dir", "logs")

    actions_path = _resolve_log_path(
        settings.get(
            "actions_log_file",
            f"{log_dir}/actions.log",
        )
    )
    parser_path = _resolve_log_path(
        settings.get(
            "parser_log_file",
            f"{log_dir}/parser.log",
        )
    )

    level_name = str(settings.get("log_level", "INFO")).upper()
    level = getattr(logging, level_name, None)

    if not isinstance(level, int):
        raise ValueError(f"Некорректный уровень логирования: {level_name}.")

    log_format = settings.get(
        "log_format",
        "%(levelname)s %(asctime)s %(name)s %(message)s",
    )

    formatter = logging.Formatter(log_format)

    # Основной журнал действий приложения.
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    app_logger.setLevel(logging.DEBUG)

    _add_file_handler(
        app_logger,
        actions_path,
        level,
        formatter,
    )

    # Отдельный журнал Parser Service.
    parser_logger = logging.getLogger(PARSER_LOGGER_NAME)
    parser_logger.setLevel(logging.DEBUG)

    # Не передаём сообщения Parser Service в actions.log.
    parser_logger.propagate = False

    _add_file_handler(
        parser_logger,
        parser_path,
        logging.DEBUG,
        formatter,
    )


@contextmanager
def parser_console_logging() -> Iterator[None]:
    """Временно выводить сообщения Parser Service в консоль."""
    parser_logger = logging.getLogger(PARSER_LOGGER_NAME)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    parser_logger.addHandler(handler)

    try:
        yield
    finally:
        parser_logger.removeHandler(handler)
        handler.close()
