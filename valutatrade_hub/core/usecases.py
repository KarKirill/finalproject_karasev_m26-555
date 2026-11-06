"""Бизнес-логика валютного кошелька."""

from valutatrade_hub.core.exceptions import (
    InvalidPasswordError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from valutatrade_hub.core.models import User
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
