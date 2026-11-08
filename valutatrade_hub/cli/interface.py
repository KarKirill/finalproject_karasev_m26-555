"""Интерактивный консольный интерфейс ValutaTrade Hub."""

import shlex
from getpass import getpass

from valutatrade_hub.cli.commands import build_parser
from valutatrade_hub.core.exceptions import ValutaTradeError
from valutatrade_hub.core.models import User
from valutatrade_hub.core.usecases import login, register
from valutatrade_hub.infra.database import DatabaseError


def _handle_register(username: str) -> None:
    """Зарегистрировать пользователя с подтверждением пароля."""
    password = getpass("Введите пароль: ")
    confirmation = getpass("Повторите пароль: ")

    if password != confirmation:
        raise ValueError("Введённые пароли не совпадают.")

    user = register(username, password)

    print(f"Пользователь '{user.username}' успешно зарегистрирован.")


def _handle_login(username: str) -> User:
    """Авторизовать пользователя и вернуть его для текущей сессии."""
    password = getpass("Введите пароль: ")
    user = login(username, password)

    print(f"Вход выполнен. Пользователь: {user.username}.")

    return user


def run() -> None:
    """Запустить интерактивную консоль приложения."""
    parser = build_parser()
    current_user: User | None = None

    print("Добро пожаловать в ValutaTrade Hub!")
    print("Введите help для просмотра доступных команд.")

    while True:
        try:
            command_line = input("\nValutaTrade> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nРабота приложения завершена.")
            break

        if not command_line:
            continue

        try:
            arguments = shlex.split(command_line)
            args = parser.parse_args(arguments)
        except ValueError as error:
            print(f"Ошибка команды: {error}")
            continue
        except SystemExit as error:
            # argparse вызывает SystemExit(0) при запросе --help.
            # Справка не должна завершать интерактивную сессию.
            if error.code != 0:
                print("Не удалось обработать команду.")
            continue

        if args.command == "exit":
            print("Работа приложения завершена.")
            break

        if args.command == "help":
            parser.print_help()
            continue

        try:
            if args.command == "register":
                _handle_register(args.username)

            elif args.command == "login":
                current_user = _handle_login(args.username)

            elif (
                args.command in ("show-portfolio", "buy", "sell")
                and current_user is None
            ):
                print("Сначала выполните вход командой login.")

            else:
                print(f"Команда '{args.command}' будет подключена на следующем этапе.")

        except (ValutaTradeError, DatabaseError, ValueError) as error:
            print(f"Ошибка: {error}")

        except (EOFError, KeyboardInterrupt):
            print("\nОперация отменена.")
