"""Интерактивный консольный интерфейс ValutaTrade Hub."""

import shlex
from getpass import getpass

from prettytable import PrettyTable

from valutatrade_hub.cli.commands import build_parser
from valutatrade_hub.core.exceptions import ValutaTradeError
from valutatrade_hub.core.models import User
from valutatrade_hub.core.usecases import (
    buy,
    get_rate,
    login,
    register,
    sell,
    show_portfolio,
)
from valutatrade_hub.infra.database import DatabaseError
from valutatrade_hub.parser_service.config import (
    BASE_CURRENCY,
    SUPPORTED_CRYPTO_CURRENCIES,
    SUPPORTED_FIAT_CURRENCIES,
)
from valutatrade_hub.parser_service.storage import RatesStorage
from valutatrade_hub.parser_service.updater import RatesUpdater


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


def _handle_show_portfolio(
    user_id: int,
    base_currency: str,
) -> None:
    """Показать валютный портфель и его общую стоимость."""
    portfolio, total_value = show_portfolio(
        user_id,
        base_currency,
    )

    wallets = portfolio.wallets

    if not wallets:
        print("Ваш портфель пока пуст.")
        print(f"Общая стоимость: 0.00 {base_currency}")
        return

    table = PrettyTable()
    table.field_names = [
        "Валюта",
        "Баланс",
        f"Курс к {base_currency}",
        f"Стоимость ({base_currency})",
    ]

    for code, wallet in sorted(wallets.items()):
        balance = wallet.balance

        if balance == 0:
            rate_text = "—"
            value = 0.0
        else:
            rate = get_rate(code, base_currency)
            rate_text = f"{rate:.8f}"
            value = balance * rate

        table.add_row(
            [
                code,
                f"{balance:.8f}",
                rate_text,
                f"{value:.2f}",
            ]
        )

    print("\nВаш валютный портфель:")
    print(table)
    print(f"Общая стоимость: {total_value:.2f} {base_currency}")


def _handle_buy(user_id: int, currency_code: str, amount: float) -> None:
    """Выполнить покупку валюты и показать результат."""
    result = buy(user_id, currency_code, amount)

    print(f"\nПокупка {result['currency_code']} выполнена успешно.")
    print(f"Количество: {result['amount']:.8f}")
    print(f"Курс: {result['rate_usd']:.8f} USD")
    print(f"Стоимость покупки: {result['total_usd']:.2f} USD")
    print(f"Текущий баланс: {result['balance']:.8f} {result['currency_code']}")


def _handle_sell(user_id: int, currency_code: str, amount: float) -> None:
    """Выполнить продажу валюты и показать результат."""
    result = sell(user_id, currency_code, amount)

    print(f"\nПродажа {result['currency_code']} выполнена успешно.")
    print(f"Количество: {result['amount']:.8f}")
    print(f"Курс: {result['rate_usd']:.8f} USD")
    print(f"Стоимость продажи: {result['total_usd']:.2f} USD")
    print(f"Текущий баланс: {result['balance']:.8f} {result['currency_code']}")


def _handle_get_rate(from_code: str, to_code: str) -> None:
    """Показать актуальный курс валютной пары."""
    rate = get_rate(from_code, to_code)

    print(f"\nАктуальный курс {from_code}/{to_code}:")
    print(f"1 {from_code} = {rate:.8f} {to_code}")


def _handle_update_rates() -> None:
    """Принудительно обновить курсы валют и показать результат."""
    updater = RatesUpdater()
    result = updater.run_update()

    print("\nОбновление курсов завершено.")
    print(f"Обновлено валютных пар: {result['updated_count']}")
    print(f"Время обновления: {result['last_refresh']}")

    errors = result["errors"]

    if errors:
        print("\nНекоторые источники завершились с ошибками:")

        for source, reason in errors.items():
            print(f"  {source}: {reason}")
    else:
        print("Все источники обработаны успешно.")


def _handle_show_rates(top: int) -> None:
    """Показать сохранённые курсы и рейтинг криптовалют."""
    snapshot = RatesStorage().load_rates()
    pairs = snapshot["pairs"]

    if not pairs:
        print("Курсы пока не загружены. Выполните update-rates.")
        return

    def make_table(codes: list[str]) -> PrettyTable:
        """Сформировать таблицу для выбранных валют."""
        table = PrettyTable()
        table.field_names = [
            "Валюта",
            f"Курс к {BASE_CURRENCY}",
            "Источник",
            "Обновлено (UTC)",
        ]

        for code in codes:
            pair = f"{code}_{BASE_CURRENCY}"
            record = pairs[pair]

            table.add_row(
                [
                    code,
                    f"{record['rate']:.8f}",
                    record.get("source", "Неизвестен"),
                    record.get("updated_at", "Нет данных"),
                ]
            )

        return table

    fiat_codes = sorted(
        code
        for code in SUPPORTED_FIAT_CURRENCIES
        if code != BASE_CURRENCY and f"{code}_{BASE_CURRENCY}" in pairs
    )

    crypto_codes = sorted(
        (
            code
            for code in SUPPORTED_CRYPTO_CURRENCIES
            if f"{code}_{BASE_CURRENCY}" in pairs
        ),
        key=lambda code: pairs[f"{code}_{BASE_CURRENCY}"]["rate"],
        reverse=True,
    )[:top]

    print("\nСохранённые курсы валют:")

    if fiat_codes:
        print("\nФиатные валюты:")
        print(make_table(fiat_codes))
    else:
        print("Курсы фиатных валют отсутствуют.")

    if crypto_codes:
        print(f"\nТоп-{top} криптовалют по стоимости:")
        print(make_table(crypto_codes))
    else:
        print("Курсы криптовалют отсутствуют.")

    print(f"\nПоследнее обновление: {snapshot.get('last_refresh')}")


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

            elif args.command == "show-portfolio":
                _handle_show_portfolio(
                    current_user.user_id,
                    args.base,
                )

            elif args.command == "buy":
                _handle_buy(
                    current_user.user_id,
                    args.currency,
                    args.amount,
                )

            elif args.command == "sell":
                _handle_sell(
                    current_user.user_id,
                    args.currency,
                    args.amount,
                )

            elif args.command == "get-rate":
                _handle_get_rate(
                    args.from_code,
                    args.to_code,
                )

            elif args.command == "update-rates":
                _handle_update_rates()

            elif args.command == "show-rates":
                _handle_show_rates(args.top)

            else:
                print(f"Команда '{args.command}' будет подключена на следующем этапе.")

        except (ValutaTradeError, DatabaseError, ValueError) as error:
            print(f"Ошибка: {error}")

        except (EOFError, KeyboardInterrupt):
            print("\nОперация отменена.")
