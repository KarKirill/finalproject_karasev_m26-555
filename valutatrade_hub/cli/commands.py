"""Разбор команд консольного интерфейса ValutaTrade Hub."""

import argparse

from valutatrade_hub.core.currencies import SUPPORTED_CURRENCY_CODES


class CommandParser(argparse.ArgumentParser):
    """Парсер с понятными русскоязычными сообщениями об ошибках."""

    def error(self, message: str) -> None:
        """Сообщить об ошибке аргументов без завершения приложения."""
        raise ValueError(
            "Неверная команда или аргументы. "
            "Введите help для просмотра доступных команд."
        )


def _currency_code(value: str) -> str:
    """Проверить и нормализовать код валюты."""
    code = value.strip().upper()

    if code not in SUPPORTED_CURRENCY_CODES:
        raise argparse.ArgumentTypeError(f"Неподдерживаемая валюта: {code}.")

    return code


def _positive_integer(value: str) -> int:
    """Проверить положительное целое число."""
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Необходимо указать целое число.") from error

    if number <= 0:
        raise argparse.ArgumentTypeError("Число должно быть положительным.")

    return number


def build_parser() -> CommandParser:
    """Создать парсер команд приложения."""
    parser = CommandParser(
        prog="ValutaTrade Hub",
        description="Консольное приложение для торговли валютами.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    # Регистрация и авторизация.
    register_parser = subparsers.add_parser(
        "register",
        help="Зарегистрировать нового пользователя.",
    )
    register_parser.add_argument(
        "username",
        help="Имя пользователя.",
    )

    login_parser = subparsers.add_parser(
        "login",
        help="Войти в учётную запись.",
    )
    login_parser.add_argument(
        "username",
        help="Имя пользователя.",
    )

    # Просмотр портфеля.
    portfolio_parser = subparsers.add_parser(
        "show-portfolio",
        help="Показать валютный портфель.",
    )
    portfolio_parser.add_argument(
        "--base",
        type=_currency_code,
        default="USD",
        help="Валюта оценки портфеля (по умолчанию USD).",
    )

    # Покупка и продажа валют.
    for command_name, description in (
        ("buy", "Купить валюту."),
        ("sell", "Продать валюту."),
    ):
        trade_parser = subparsers.add_parser(
            command_name,
            help=description,
        )
        trade_parser.add_argument(
            "currency",
            type=_currency_code,
            help="Код валюты.",
        )
        trade_parser.add_argument(
            "amount",
            type=float,
            help="Количество валюты.",
        )

    # Получение курса валютной пары.
    rate_parser = subparsers.add_parser(
        "get-rate",
        help="Получить актуальный валютный курс.",
    )
    rate_parser.add_argument(
        "from_code",
        type=_currency_code,
        help="Исходная валюта.",
    )
    rate_parser.add_argument(
        "to_code",
        type=_currency_code,
        help="Целевая валюта.",
    )

    # Обновление курсов.
    subparsers.add_parser(
        "update-rates",
        help="Принудительно обновить курсы валют.",
    )

    # Просмотр сохранённых курсов.
    rates_parser = subparsers.add_parser(
        "show-rates",
        help="Показать сохранённые валютные курсы.",
    )
    rates_parser.add_argument(
        "--top",
        type=_positive_integer,
        default=5,
        help="Количество криптовалют в рейтинге.",
    )

    # Служебные команды.
    subparsers.add_parser(
        "help",
        help="Показать справку по командам.",
    )

    subparsers.add_parser(
        "exit",
        help="Завершить работу приложения.",
    )

    return parser
