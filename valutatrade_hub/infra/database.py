import copy
import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from valutatrade_hub.infra.settings import SettingsLoader


class DatabaseError(Exception):
    """Ошибка при чтении или записи данных."""


class DatabaseManager:
    """Единая точка доступа к JSON-хранилищам проекта."""

    _instance = None
    _instance_lock = RLock()

    def __new__(cls, *args: Any, **kwargs: Any) -> "DatabaseManager":
        """Создаёт единственный экземпляр DatabaseManager."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)

        return cls._instance

    def __init__(self, data_dir: str | Path | None = None) -> None:
        """Инициализирует пути к JSON-хранилищам."""
        if getattr(self, "_initialized", False):
            return

        project_root = Path(__file__).resolve().parents[2]

        if data_dir is None:
            data_dir = SettingsLoader().get("data_dir", "data")

        directory = Path(data_dir)

        self._data_dir = (
            directory if directory.is_absolute() else project_root / directory
        )

        self._paths = {
            "users": self._data_dir / "users.json",
            "portfolios": self._data_dir / "portfolios.json",
            "rates": self._data_dir / "rates.json",
            "exchange_rates": self._data_dir / "exchange_rates.json",
        }

        self._io_lock = RLock()
        self._initialized = True

    def get_path(self, name: str) -> Path:
        """Возвращает путь к хранилищу по его имени."""
        if name not in self._paths:
            raise ValueError(f"Неизвестное хранилище: {name}")

        return self._paths[name]

    def _read_json(self, name: str, default: Any = None) -> Any:
        """Безопасно читает JSON-файл."""
        path = self.get_path(name)

        if not path.exists():
            return copy.deepcopy(default)

        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            raise DatabaseError(f"Не удалось прочитать {path.name}: {error}") from error

    def load_json(self, name: str, default: Any = None) -> Any:
        """Читает JSON-данные с блокировкой доступа."""
        with self._io_lock:
            return self._read_json(name, default)

    def _write_json(self, name: str, data: Any) -> None:
        """Атомарно записывает данные в JSON-файл."""
        path = self.get_path(name)
        temporary_path = None

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)

                json.dump(
                    data,
                    temporary_file,
                    ensure_ascii=False,
                    indent=4,
                    allow_nan=False,
                )
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temporary_path, path)

        except (OSError, TypeError, ValueError) as error:
            raise DatabaseError(f"Не удалось записать {path.name}: {error}") from error

        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def save_json(self, name: str, data: Any) -> None:
        """Сохраняет JSON-данные с блокировкой доступа."""
        with self._io_lock:
            self._write_json(name, data)

    def update_json(
        self,
        name: str,
        updater: Callable[[Any], Any],
        default: Any = None,
    ) -> Any:
        """Выполняет безопасную операцию чтение-изменение-запись."""
        with self._io_lock:
            data = self._read_json(name, default)
            updated_data = updater(data)
            self._write_json(name, updated_data)

            return copy.deepcopy(updated_data)

    def load_users(self) -> list:
        """Загружает список пользователей."""
        return self.load_json("users", [])

    def save_users(self, users: list) -> None:
        """Сохраняет список пользователей."""
        self.save_json("users", users)

    def load_portfolios(self) -> list:
        """Загружает список портфелей."""
        return self.load_json("portfolios", [])

    def save_portfolios(self, portfolios: list) -> None:
        """Сохраняет список портфелей."""
        self.save_json("portfolios", portfolios)

    def load_rates(self) -> dict:
        """Загружает актуальный кеш курсов."""
        return self.load_json(
            "rates",
            {"pairs": {}, "last_refresh": None},
        )

    def save_rates(self, rates: dict) -> None:
        """Сохраняет актуальный кеш курсов."""
        self.save_json("rates", rates)

    def load_exchange_rates(self) -> list:
        """Загружает историю курсов."""
        return self.load_json("exchange_rates", [])

    def save_exchange_rates(self, history: list) -> None:
        """Сохраняет историю курсов."""
        self.save_json("exchange_rates", history)
