class ValutaTradeError(Exception):
    """Базовое исключение приложения ValutaTrade Hub."""


class InsufficientFundsError(ValutaTradeError):
    """Возникает при недостатке средств."""

    def __init__(
        self,
        available: float,
        required: float,
        code: str,
    ) -> None:
        self.available = available
        self.required = required
        self.code = code

        super().__init__(
            f"Недостаточно средств: доступно {available:.4f} {code}, "
            f"требуется {required:.4f} {code}"
        )


class UserAlreadyExistsError(ValutaTradeError):
    """Возникает при регистрации существующего пользователя."""


class UserNotFoundError(ValutaTradeError):
    """Возникает при поиске несуществующего пользователя."""


class InvalidPasswordError(ValutaTradeError):
    """Возникает при неправильном пароле."""


class CurrencyNotFoundError(ValutaTradeError):
    """Возникает при обращении к неизвестной валюте."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Неизвестная валюта '{code}'")


class WalletNotFoundError(ValutaTradeError):
    """Возникает при отсутствии кошелька пользователя."""


class ApiRequestError(ValutaTradeError):
    """Возникает при ошибке обращения к внешнему API."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")
