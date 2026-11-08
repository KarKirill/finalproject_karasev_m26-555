"""Интерактивный консольный интерфейс ValutaTrade Hub."""

import logging
import math
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
from valutatrade_hub.logging_config import parser_console_logging
from valutatrade_hub.parser_service.config import (
    BASE_CURRENCY,
    SUPPORTED_CRYPTO_CURRENCIES,
    SUPPORTED_FIAT_CURRENCIES,
)
from valutatrade_hub.parser_service.storage import RatesStorage
from valutatrade_hub.parser_service.updater import RatesUpdater

logger = logging.getLogger(__name__)


def _handle_register(username: str, password: str | None = None) -> None:
    """Зарегистрировать пользователя с интерактивным или заданным паролем."""
    if password is None:
        password = getpass("Введите пароль: ")
        confirmation = getpass("Повторите пароль: ")

        if password != confirmation:
            raise ValueError("Введённые пароли не совпадают.")

    user = register(username, password)

    logger.info(
        "Зарегистрирован пользователь: ID=%s, имя=%s.",
        user.user_id,
        user.username,
    )

    print(f"Пользователь '{user.username}' успешно зарегистрирован.")


def _handle_login(username: str, password: str | None = None) -> User:
    """Авторизовать пользователя и вернуть его для текущей сессии."""
    if password is None:
        password = getpass("Введите пароль: ")

    user = login(username, password)

    logger.info(
        "Успешная авторизация: ID=%s, имя=%s.",
        user.user_id,
        user.username,
    )

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


def _handle_update_rates(source: str | None = None) -> None:
    """Обновить курсы выбранного источника или всех источников."""
    updater = RatesUpdater()

    # Временно показываем сообщения Parser Service в консоли.
    with parser_console_logging():
        result = updater.run_update(source=source)

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


def _handle_show_rates(
    top: int | None,
    currency_code: str | None = None,
    base_currency: str = BASE_CURRENCY,
) -> None:
    """Показать сохранённые курсы с фильтрацией и конвертацией."""
    if currency_code is not None and top is not None:
        raise ValueError(
            "Параметры --currency и --top нельзя использовать одновременно."
        )

    snapshot = RatesStorage().load_rates()
    pairs = snapshot["pairs"]

    if not pairs:
        print("Локальный кеш курсов пуст. Выполните update-rates.")
        return

    def get_cached_usd_rate(code: str) -> float:
        """Получить курс валюты к USD исключительно из локального кеша."""
        if code == BASE_CURRENCY:
            return 1.0

        record = pairs.get(f"{code}_{BASE_CURRENCY}")

        if not isinstance(record, dict):
            raise ValueError(f"Курс для '{code}' не найден в кеше.")

        rate = record.get("rate")

        if (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float))
            or not math.isfinite(rate)
            or rate <= 0
        ):
            raise ValueError(f"Некорректный курс для '{code}' в кеше.")

        return float(rate)

    # Проверяем, что курс выбранной базовой валюты имеется в кеше.
    base_usd_rate = get_cached_usd_rate(base_currency)

    def make_table(codes: list[str]) -> PrettyTable:
        """Сформировать таблицу с курсами в выбранной базе."""
        table = PrettyTable()
        table.field_names = [
            "Валюта",
            f"Курс к {base_currency}",
            "Источник",
            "Обновлено (UTC)",
        ]

        for code in codes:
            usd_rate = get_cached_usd_rate(code)
            converted_rate = usd_rate / base_usd_rate

            record = pairs.get(f"{code}_{BASE_CURRENCY}", {})

            table.add_row(
                [
                    code,
                    f"{converted_rate:.8f}",
                    record.get("source", "Расчётный курс"),
                    record.get("updated_at", "Нет данных"),
                ]
            )

        return table

    print(f"\nСохранённые курсы относительно {base_currency}:")

    # Фильтрация по одной конкретной валюте.
    if currency_code is not None:
        print(make_table([currency_code]))
        print(f"\nПоследнее обновление: {snapshot.get('last_refresh')}")
        return

    # Фиатные валюты показываем по алфавиту.
    fiat_codes = sorted(
        code
        for code in SUPPORTED_FIAT_CURRENCIES
        if code != BASE_CURRENCY and f"{code}_{BASE_CURRENCY}" in pairs
    )

    # Криптовалюты сортируем по стоимости относительно USD.
    crypto_codes = sorted(
        (
            code
            for code in SUPPORTED_CRYPTO_CURRENCIES
            if f"{code}_{BASE_CURRENCY}" in pairs
        ),
        key=get_cached_usd_rate,
        reverse=True,
    )

    # Ограничение количества криптовалют применяется только при --top.
    if top is not None:
        crypto_codes = crypto_codes[:top]

    if fiat_codes:
        print("\nФиатные валюты:")
        print(make_table(fiat_codes))
    else:
        print("Курсы фиатных валют отсутствуют.")

    if crypto_codes:
        if top is None:
            print("\nКриптовалюты:")
        else:
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
                _handle_register(args.username, args.password)

            elif args.command == "login":
                current_user = _handle_login(args.username, args.password)

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
                _handle_update_rates(args.source)

            elif args.command == "show-rates":
                _handle_show_rates(
                    args.top,
                    args.currency,
                    args.base,
                )

            else:
                print(f"Команда '{args.command}' будет подключена на следующем этапе.")

        except (ValutaTradeError, DatabaseError, ValueError) as error:
            logger.warning(
                "Ошибка выполнения команды %s: %s",
                args.command,
                error,
            )
            print(f"Ошибка: {error}")

        except (EOFError, KeyboardInterrupt):
            print("\nОперация отменена.")
