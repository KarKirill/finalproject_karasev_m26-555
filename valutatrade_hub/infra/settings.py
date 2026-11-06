"""Загрузка и кеширование конфигурации приложения."""

import tomllib
from pathlib import Path
from threading import RLock
from typing import Any


class SettingsLoader:
    """Singleton для загрузки настроек из pyproject.toml."""

    _instance = None
    _instance_lock = RLock()

    DEFAULT_SETTINGS = {
        "data_dir": "data",
        "rates_ttl_seconds": 3600,
        "base_currency": "USD",
        "log_dir": "logs",
        "log_level": "INFO",
        "log_format": "%(levelname)s %(asctime)s %(name)s %(message)s",
        "actions_log_file": "logs/actions.log",
        "parser_log_file": "logs/parser.log",
        "api_timeout": 10,
    }

    def __new__(cls) -> "SettingsLoader":
        """Создаёт единственный экземпляр класса."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)

        return cls._instance

    def __init__(self) -> None:
        """Инициализирует настройки приложения один раз."""
        if getattr(self, "_initialized", False):
            return

        self._project_root = Path(__file__).resolve().parents[2]
        self._config_path = self._project_root / "pyproject.toml"
        self._settings: dict[str, Any] = {}

        self.reload()
        self._initialized = True

    def reload(self) -> None:
        """Перечитывает конфигурацию из pyproject.toml."""
        settings = self.DEFAULT_SETTINGS.copy()

        try:
            with self._config_path.open("rb") as config_file:
                config = tomllib.load(config_file)
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise RuntimeError(f"Не удалось загрузить конфигурацию: {error}") from error

        project_settings = config.get("tool", {}).get("valutatrade", {})

        if not isinstance(project_settings, dict):
            raise RuntimeError("Некорректная секция [tool.valutatrade].")

        settings.update(project_settings)
        self._settings = settings

    def get(self, key: str, default: Any = None) -> Any:
        """Возвращает значение настройки или значение по умолчанию."""
        return self._settings.get(key, default)
