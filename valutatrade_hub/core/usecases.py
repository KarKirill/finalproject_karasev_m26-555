"""Бизнес-логика валютного кошелька."""

import math

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import (
    InvalidPasswordError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.infra.database import DatabaseError, DatabaseManager


def _normalize_username(username: str) -> str:
    """Проверяет и нормализует имя пользователя."""
    if not isinstance(username, str) or not username.strip():
        raise ValueError("Имя пользователя не может быть пустым.")

    return username.strip()


def _user_from_record(record: dict) -> User:
    """Восстанавливает объект User из JSON-записи."""
    try:
        return User(
            user_id=record["user_id"],
            username=record["username"],
            hashed_password=record["hashed_password"],
            salt=record["salt"],
            registration_date=record["registration_date"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise DatabaseError("Некорректные данные пользователя в хранилище.") from error


def get_user_by_username(username: str) -> User | None:
    """Находит пользователя по имени."""
    normalized_username = _normalize_username(username)
    database = DatabaseManager()

    users = database.load_users()

    if not isinstance(users, list):
        raise DatabaseError("Некорректный формат users.json.")

    for record in users:
        if (
            isinstance(record, dict)
            and isinstance(record.get("username"), str)
            and record["username"].casefold() == normalized_username.casefold()
        ):
            return _user_from_record(record)

    return None


def get_user_by_id(user_id: int) -> User | None:
    """Находит пользователя по идентификатору."""
    database = DatabaseManager()
    users = database.load_users()

    if not isinstance(users, list):
        raise DatabaseError("Некорректный формат users.json.")

    for record in users:
        if isinstance(record, dict) and record.get("user_id") == user_id:
            return _user_from_record(record)

    return None


def register(username: str, password: str) -> User:
    """Регистрирует пользователя и создаёт пустой портфель."""
    normalized_username = _normalize_username(username)
    database = DatabaseManager()

    def add_user(users: list) -> list:
        if not isinstance(users, list):
            raise DatabaseError("Некорректный формат users.json.")

        for record in users:
            if (
                isinstance(record, dict)
                and isinstance(record.get("username"), str)
                and record["username"].casefold() == normalized_username.casefold()
            ):
                raise UserAlreadyExistsError(
                    f"Пользователь '{normalized_username}' уже существует."
                )

        existing_ids = [
            record["user_id"]
            for record in users
            if (
                isinstance(record, dict)
                and isinstance(record.get("user_id"), int)
                and not isinstance(record["user_id"], bool)
                and record["user_id"] > 0
            )
        ]

        user_id = max(existing_ids, default=0) + 1

        user = User.create(
            user_id=user_id,
            username=normalized_username,
            password=password,
        )

        users.append(user.to_dict())

        return users

    updated_users = database.update_json(
        "users",
        add_user,
        default=[],
    )

    user_record = next(
        record for record in updated_users if record["username"] == normalized_username
    )

    user = _user_from_record(user_record)

    def add_portfolio(portfolios: list) -> list:
        if not isinstance(portfolios, list):
            raise DatabaseError("Некорректный формат portfolios.json.")

        portfolios.append(
            {
                "user_id": user.user_id,
                "wallets": {},
            }
        )

        return portfolios

    database.update_json(
        "portfolios",
        add_portfolio,
        default=[],
    )

    return user


def login(username: str, password: str) -> User:
    """Проверяет учётные данные и возвращает пользователя."""
    user = get_user_by_username(username)

    if user is None:
        raise UserNotFoundError(f"Пользователь '{username}' не найден.")

    if not user.verify_password(password):
        raise InvalidPasswordError("Неверный пароль.")

    return user


def _portfolio_from_record(record: dict, user: User) -> Portfolio:
    """Восстанавливает объект Portfolio из JSON-записи."""
    if not isinstance(record, dict):
        raise DatabaseError("Некорректная запись портфеля.")

    if record.get("user_id") != user.user_id:
        raise DatabaseError("ID пользователя в портфеле не совпадает.")

    wallets_data = record.get("wallets", {})

    if not isinstance(wallets_data, dict):
        raise DatabaseError("Некорректный формат кошельков.")

    try:
        wallets = {
            code: Wallet(
                currency_code=code,
                balance=wallet_data["balance"],
            )
            for code, wallet_data in wallets_data.items()
            if isinstance(wallet_data, dict)
        }

        if len(wallets) != len(wallets_data):
            raise ValueError("Некорректная запись кошелька.")

        return Portfolio(
            user_id=user.user_id,
            wallets=wallets,
            user=user,
        )

    except (KeyError, TypeError, ValueError) as error:
        raise DatabaseError("Не удалось восстановить портфель пользователя.") from error


def show_portfolio(
    user_id: int,
    base_currency: str = "USD",
) -> tuple[Portfolio, float]:
    """Возвращает портфель пользователя и его общую стоимость."""
    database = DatabaseManager()

    user = get_user_by_id(user_id)

    if user is None:
        raise UserNotFoundError(f"Пользователь с ID {user_id} не найден.")

    portfolios = database.load_portfolios()

    if not isinstance(portfolios, list):
        raise DatabaseError("Некорректный формат portfolios.json.")

    portfolio_record = next(
        (
            record
            for record in portfolios
            if isinstance(record, dict) and record.get("user_id") == user_id
        ),
        None,
    )

    if portfolio_record is None:
        raise DatabaseError(f"Портфель пользователя {user_id} не найден.")

    portfolio = _portfolio_from_record(portfolio_record, user)

    rates = database.load_rates()

    if not isinstance(rates, dict):
        raise DatabaseError("Некорректный формат rates.json.")

    total_value = portfolio.get_total_value(
        base_currency=base_currency,
        rates=rates,
    )

    return portfolio, total_value


def _validate_amount(amount: float) -> None:
    """Проверяет корректность денежной суммы."""
    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
        or amount <= 0
    ):
        raise ValueError("Сумма должна быть положительным числом.")


def buy(user_id: int, currency_code: str, amount: float) -> dict:
    """Покупает валюту, увеличивая баланс соответствующего кошелька."""
    user = get_user_by_id(user_id)

    if user is None:
        raise UserNotFoundError(f"Пользователь с ID {user_id} не найден.")

    currency = get_currency(currency_code)
    _validate_amount(amount)

    database = DatabaseManager()

    def update_portfolio(portfolios: list) -> list:
        if not isinstance(portfolios, list):
            raise DatabaseError("Некорректный формат portfolios.json.")

        for index, record in enumerate(portfolios):
            if isinstance(record, dict) and record.get("user_id") == user_id:
                portfolio = _portfolio_from_record(record, user)

                if currency.code not in portfolio.wallets:
                    portfolio.add_currency(currency.code)

                wallet = portfolio.wallets[currency.code]
                wallet.deposit(amount)

                portfolios[index] = portfolio.to_dict()

                return portfolios

        raise DatabaseError(f"Портфель пользователя {user_id} не найден.")

    updated_portfolios = database.update_json(
        "portfolios",
        update_portfolio,
        default=[],
    )

    updated_record = next(
        record for record in updated_portfolios if record["user_id"] == user_id
    )

    portfolio = _portfolio_from_record(updated_record, user)
    wallet = portfolio.wallets[currency.code]

    return {
        "user_id": user_id,
        "currency_code": currency.code,
        "amount": float(amount),
        "balance": wallet.balance,
    }
