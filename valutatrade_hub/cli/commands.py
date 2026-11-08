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

    def parse_args(
        self,
        args: list[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace:
        """Разобрать и объединить позиционные и именованные аргументы."""
        parsed = super().parse_args(args, namespace)

        required_fields = {
            "register": (("username", "--username"),),
            "login": (("username", "--username"),),
            "buy": (
                ("currency", "--currency"),
                ("amount", "--amount"),
            ),
            "sell": (
                ("currency", "--currency"),
                ("amount", "--amount"),
            ),
            "get-rate": (
                ("from_code", "--from"),
                ("to_code", "--to"),
            ),
        }

        for field_name, option_name in required_fields.get(parsed.command, ()):
            positional_value = getattr(parsed, field_name)
            option_field = f"option_{field_name}"
            option_value = getattr(parsed, option_field)

            if positional_value is not None and option_value is not None:
                self.error(f"Параметр {option_name} указан дважды.")

            value = option_value if option_value is not None else positional_value

            if value is None:
                self.error(f"Не указан обязательный параметр {option_name}.")

            setattr(parsed, field_name, value)
            delattr(parsed, option_field)

        return parsed


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


def _add_dual_argument(
    command_parser: CommandParser,
    name: str,
    option: str,
    **kwargs: object,
) -> None:
    """Разрешить позиционную и именованную формы одного аргумента."""
    command_parser.add_argument(name, nargs="?", **kwargs)
    command_parser.add_argument(
        option,
        dest=f"option_{name}",
        **kwargs,
    )


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
    for command_name, description in (
        ("register", "Зарегистрировать нового пользователя."),
        ("login", "Войти в учётную запись."),
    ):
        auth_parser = subparsers.add_parser(
            command_name,
            help=description,
        )

        _add_dual_argument(
            auth_parser,
            "username",
            "--username",
            help="Имя пользователя.",
        )

        auth_parser.add_argument(
            "--password",
            default=None,
            help="Пароль (если не указан, вводится интерактивно).",
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

        _add_dual_argument(
            trade_parser,
            "currency",
            "--currency",
            type=_currency_code,
            help="Код валюты.",
        )

        _add_dual_argument(
            trade_parser,
            "amount",
            "--amount",
            type=float,
            help="Количество валюты.",
        )

    # Получение курса валютной пары.
    rate_parser = subparsers.add_parser(
        "get-rate",
        help="Получить актуальный валютный курс.",
    )

    _add_dual_argument(
        rate_parser,
        "from_code",
        "--from",
        type=_currency_code,
        help="Исходная валюта.",
    )

    _add_dual_argument(
        rate_parser,
        "to_code",
        "--to",
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
