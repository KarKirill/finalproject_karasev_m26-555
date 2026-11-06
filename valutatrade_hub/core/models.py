import hashlib
import hmac
import math
import secrets
from datetime import datetime, timezone

from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.utils import get_usd_rate


class User:
    """Представляет пользователя валютной платформы."""

    MIN_PASSWORD_LENGTH = 4
    HASH_ITERATIONS = 200_000

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime | str,
    ) -> None:
        """Инициализирует пользователя."""
        if isinstance(user_id, bool) or not isinstance(user_id, int):
            raise TypeError("ID пользователя должен быть целым числом.")

        if user_id <= 0:
            raise ValueError("ID пользователя должен быть положительным.")

        self._user_id = user_id
        self.username = username
        self._hashed_password = self._validate_string(hashed_password, "Хеш пароля")
        self._salt = self._validate_string(salt, "Соль")
        self._registration_date = self._parse_date(registration_date)

    @classmethod
    def create(
        cls,
        user_id: int,
        username: str,
        password: str,
        registration_date: datetime | None = None,
    ) -> "User":
        """Создаёт пользователя с новым хешем пароля."""
        cls._validate_password(password)

        salt = secrets.token_hex(16)
        hashed_password = cls._hash_password(password, salt)

        return cls(
            user_id=user_id,
            username=username,
            hashed_password=hashed_password,
            salt=salt,
            registration_date=registration_date or datetime.now(timezone.utc),
        )

    @classmethod
    def _hash_password(cls, password: str, salt: str) -> str:
        """Создаёт хеш пароля с использованием PBKDF2-HMAC-SHA256."""
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            cls.HASH_ITERATIONS,
        ).hex()

    @classmethod
    def _validate_password(cls, password: str) -> None:
        """Проверяет минимальную длину пароля."""
        if not isinstance(password, str):
            raise TypeError("Пароль должен быть строкой.")

        if len(password) < cls.MIN_PASSWORD_LENGTH:
            raise ValueError("Пароль должен быть не короче 4 символов.")

    @staticmethod
    def _validate_string(value: str, field_name: str) -> str:
        """Проверяет непустую строку."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} не может быть пустым.")

        return value

    @staticmethod
    def _parse_date(value: datetime | str) -> datetime:
        """Преобразует дату регистрации в UTC."""
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))

        if not isinstance(value, datetime):
            raise TypeError("Дата регистрации должна быть datetime.")

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    @property
    def user_id(self) -> int:
        """Возвращает идентификатор пользователя."""
        return self._user_id

    @property
    def username(self) -> str:
        """Возвращает имя пользователя."""
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        """Устанавливает имя пользователя."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым.")

        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        """Возвращает хеш пароля для сохранения в хранилище."""
        return self._hashed_password

    @property
    def salt(self) -> str:
        """Возвращает соль пользователя для сохранения в хранилище."""
        return self._salt

    @property
    def registration_date(self) -> datetime:
        """Возвращает дату регистрации."""
        return self._registration_date

    def verify_password(self, password: str) -> bool:
        """Проверяет соответствие введённого пароля сохранённому хешу."""
        if not isinstance(password, str):
            return False

        candidate_hash = self._hash_password(password, self._salt)

        return hmac.compare_digest(
            self._hashed_password,
            candidate_hash,
        )

    def change_password(self, new_password: str) -> None:
        """Изменяет пароль, генерируя новую соль и хеш."""
        self._validate_password(new_password)

        new_salt = secrets.token_hex(16)
        new_hash = self._hash_password(new_password, new_salt)

        self._salt = new_salt
        self._hashed_password = new_hash

    def get_user_info(self) -> dict:
        """Возвращает информацию о пользователе без пароля и соли."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "registration_date": self._registration_date.isoformat(),
        }

    def to_dict(self) -> dict:
        """Преобразует пользователя в словарь для JSON-хранилища."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self._registration_date.isoformat(),
        }


class Wallet:
    """Представляет кошелёк пользователя для одной валюты."""

    def __init__(
        self,
        currency_code: str,
        balance: float = 0.0,
    ) -> None:
        """Инициализирует кошелёк."""
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым.")

        currency_code = currency_code.strip().upper()

        if any(char.isspace() for char in currency_code):
            raise ValueError("Код валюты не должен содержать пробелы.")

        self.currency_code = currency_code
        self.balance = balance

    @property
    def balance(self) -> float:
        """Возвращает текущий баланс."""
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        """Устанавливает баланс с проверкой корректности значения."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом.")

        if not math.isfinite(value) or value < 0:
            raise ValueError("Баланс не может быть отрицательным.")

        self._balance = float(value)

    @staticmethod
    def _validate_amount(amount: float) -> float:
        """Проверяет корректность суммы операции."""
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise TypeError("Сумма должна быть числом.")

        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Сумма должна быть положительным числом.")

        return float(amount)

    def deposit(self, amount: float) -> None:
        """Пополняет баланс кошелька."""
        amount = self._validate_amount(amount)
        self.balance = round(self.balance + amount, 8)

    def withdraw(self, amount: float) -> None:
        """Снимает средства при достаточном балансе."""
        amount = self._validate_amount(amount)

        if amount > self.balance:
            raise InsufficientFundsError(
                available=self.balance,
                required=amount,
                code=self.currency_code,
            )

        self.balance = round(self.balance - amount, 8)

    def get_balance_info(self) -> str:
        """Возвращает информацию о текущем балансе."""
        return f"{self.balance:.4f} {self.currency_code}"

    def to_dict(self) -> dict:
        """Преобразует кошелёк в словарь для JSON-хранилища."""
        return {
            "currency_code": self.currency_code,
            "balance": self.balance,
        }


class Portfolio:
    """Представляет валютный портфель одного пользователя."""

    def __init__(
        self,
        user_id: int,
        wallets: dict[str, Wallet] | None = None,
        user: User | None = None,
    ) -> None:
        """Инициализирует портфель пользователя."""
        if isinstance(user_id, bool) or not isinstance(user_id, int):
            raise TypeError("ID пользователя должен быть целым числом.")

        if user_id <= 0:
            raise ValueError("ID пользователя должен быть положительным.")

        if user is not None and not isinstance(user, User):
            raise TypeError("user должен быть объектом User.")

        if user is not None and user.user_id != user_id:
            raise ValueError("ID пользователя и портфеля не совпадают.")

        self._user_id = user_id
        self._user = user
        self._wallets: dict[str, Wallet] = {}

        if wallets is not None:
            if not isinstance(wallets, dict):
                raise TypeError("Кошельки должны быть словарём.")

            for currency_code, wallet in wallets.items():
                code = self._normalize_currency_code(currency_code)

                if not isinstance(wallet, Wallet):
                    raise TypeError("Каждый кошелёк должен быть объектом Wallet.")

                if wallet.currency_code != code:
                    raise ValueError("Код валюты кошелька не совпадает с ключом.")

                if code in self._wallets:
                    raise ValueError(f"Кошелёк {code} уже существует.")

                self._wallets[code] = wallet

    @staticmethod
    def _normalize_currency_code(currency_code: str) -> str:
        """Проверяет и нормализует код валюты."""
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым.")

        code = currency_code.strip().upper()

        if any(char.isspace() for char in code):
            raise ValueError("Код валюты не должен содержать пробелы.")

        return code

    @property
    def user(self) -> User | None:
        """Возвращает пользователя без возможности перезаписи."""
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Возвращает копию словаря кошельков."""
        return self._wallets.copy()

    def add_currency(self, currency_code: str) -> Wallet:
        """Добавляет новый кошелёк в портфель."""
        code = self._normalize_currency_code(currency_code)

        if code in self._wallets:
            raise ValueError(f"Кошелёк {code} уже существует.")

        wallet = Wallet(code)
        self._wallets[code] = wallet

        return wallet

    def get_wallet(self, currency_code: str) -> Wallet | None:
        """Возвращает кошелёк по коду валюты или None."""
        code = self._normalize_currency_code(currency_code)

        return self._wallets.get(code)

    def get_total_value(
        self,
        base_currency: str = "USD",
        rates: dict | None = None,
    ) -> float:
        """Рассчитывает общую стоимость портфеля в базовой валюте."""
        base_code = self._normalize_currency_code(base_currency)

        base_usd_rate = get_usd_rate(base_code, rates)

        total_usd = 0.0

        for wallet in self._wallets.values():
            currency_usd_rate = get_usd_rate(
                wallet.currency_code,
                rates,
            )

            total_usd += wallet.balance * currency_usd_rate

        return total_usd / base_usd_rate

    def to_dict(self) -> dict:
        """Преобразует портфель в словарь для JSON-хранилища."""
        return {
            "user_id": self._user_id,
            "wallets": {
                code: {"balance": wallet.balance}
                for code, wallet in self._wallets.items()
            },
        }
