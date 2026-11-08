"""Точка входа в приложение ValutaTrade Hub."""

from valutatrade_hub.cli.interface import run
from valutatrade_hub.infra.logging_config import setup_logging


def main() -> None:
    """Настроить логирование и запустить консольное приложение."""
    setup_logging()
    run()


if __name__ == "__main__":
    main()
