"""Бизнес-логика валютного кошелька."""

import math
from datetime import datetime, timezone

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    InvalidPasswordError,
    UserAlreadyExistsError,
    UserNotFoundError,
    WalletNotFoundError,
)
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.utils import get_usd_rate
from valutatrade_hub.infra.database import DatabaseError, DatabaseManager
from valutatrade_hub.parser_service.config import RATES_TTL_SECONDS
from valutatrade_hub.parser_service.updater import RatesUpdater


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
    """Возвращает портфель и его стоимость по актуальным курсам."""
    base_code = get_currency(base_currency).code
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
    wallets = portfolio.wallets

    # Пустой портфель не требует обращения к API.
    if not wallets or all(wallet.balance == 0 for wallet in wallets.values()):
        return portfolio, 0.0

    # Проверяем актуальность курсов валют, имеющихся в портфеле,
    # а также валюты, в которой требуется показать стоимость.
    required_codes = {code for code in wallets if code != "USD"}

    if base_code != "USD":
        required_codes.add(base_code)

    for code in sorted(required_codes):
        get_rate(code, "USD")

    # После возможного обновления читаем сохранённые курсы заново.
    rates = database.load_rates()

    if not isinstance(rates, dict) or not isinstance(rates.get("pairs"), dict):
        raise DatabaseError("Некорректный формат rates.json.")

    total_value = portfolio.get_total_value(
        base_currency=base_code,
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

    # Получаем актуальный курс до изменения баланса.
    rate_usd = get_rate(currency.code, "USD")
    total_usd = float(amount) * rate_usd

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
        "rate_usd": rate_usd,
        "total_usd": total_usd,
    }


def sell(user_id: int, currency_code: str, amount: float) -> dict:
    """Продаёт валюту, уменьшая баланс соответствующего кошелька."""
    user = get_user_by_id(user_id)

    if user is None:
        raise UserNotFoundError(f"Пользователь с ID {user_id} не найден.")

    currency = get_currency(currency_code)
    _validate_amount(amount)

    # Получаем актуальный курс до изменения баланса.
    rate_usd = get_rate(currency.code, "USD")
    total_usd = float(amount) * rate_usd

    database = DatabaseManager()

    def update_portfolio(portfolios: list) -> list:
        if not isinstance(portfolios, list):
            raise DatabaseError("Некорректный формат portfolios.json.")

        for index, record in enumerate(portfolios):
            if isinstance(record, dict) and record.get("user_id") == user_id:
                portfolio = _portfolio_from_record(record, user)

                wallet = portfolio.wallets.get(currency.code)

                if wallet is None:
                    raise WalletNotFoundError(f"Кошелёк {currency.code} не найден.")

                # withdraw самостоятельно проверяет остаток средств.
                wallet.withdraw(amount)

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
        "rate_usd": rate_usd,
        "total_usd": total_usd,
    }


def _is_fresh_usd_rate(
    currency_code: str,
    snapshot: dict,
    current_time: datetime,
) -> bool:
    """Проверяет актуальность курса валюты относительно USD."""
    if currency_code == "USD":
        return True

    pairs = snapshot.get("pairs")

    if not isinstance(pairs, dict):
        return False

    rate_data = pairs.get(f"{currency_code}_USD")

    if not isinstance(rate_data, dict):
        return False

    # Проверяем, что сохранённый курс корректен.
    try:
        get_usd_rate(currency_code, snapshot)
    except ValueError:
        return False

    updated_at = rate_data.get("updated_at")

    if not isinstance(updated_at, str):
        return False

    try:
        timestamp = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return False

    if timestamp.tzinfo is None:
        return False

    age_seconds = (current_time - timestamp.astimezone(timezone.utc)).total_seconds()

    return 0 <= age_seconds <= RATES_TTL_SECONDS


def get_rate(from_code: str, to_code: str) -> float:
    """Возвращает актуальный курс одной валюты относительно другой."""
    source_code = get_currency(from_code).code
    target_code = get_currency(to_code).code

    # Для одинаковых валют курс всегда равен единице.
    if source_code == target_code:
        return 1.0

    updater = RatesUpdater()
    snapshot = updater.storage.load_rates()
    current_time = datetime.now(timezone.utc)

    required_codes = (source_code, target_code)

    # Обновляем курсы только при отсутствии актуальных данных.
    if not all(
        _is_fresh_usd_rate(code, snapshot, current_time) for code in required_codes
    ):
        updater.update_rates()

        snapshot = updater.storage.load_rates()
        current_time = datetime.now(timezone.utc)

        # После обновления проверяем именно нужные валюты.
        if not all(
            _is_fresh_usd_rate(code, snapshot, current_time) for code in required_codes
        ):
            raise ApiRequestError(
                "Не удалось получить актуальный курс "
                f"для валютной пары {source_code}/{target_code}."
            )

    source_usd_rate = get_usd_rate(source_code, snapshot)
    target_usd_rate = get_usd_rate(target_code, snapshot)

    return source_usd_rate / target_usd_rate
