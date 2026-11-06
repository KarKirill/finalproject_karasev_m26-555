"""API-клиенты для получения курсов криптовалют и фиатных валют."""

import logging
import math
import time
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import quote

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import (
    API_TIMEOUT_SECONDS,
    BASE_CURRENCY,
    COINGECKO_BASE_URL,
    CRYPTO_ID_MAP,
    EXCHANGE_RATE_API_BASE_URL,
    EXCHANGE_RATE_API_KEY,
    SUPPORTED_FIAT_CURRENCIES,
)

logger = logging.getLogger(__name__)


class BaseApiClient(ABC):
    """Абстрактный базовый класс API-клиентов."""

    def __init__(
        self,
        timeout: float = API_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("Время ожидания запроса должно быть положительным.")

        self.timeout = timeout
        self.session = session if session is not None else requests.Session()

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Получить курсы валют в формате КОД_БАЗОВАЯ_ВАЛЮТА."""
        raise NotImplementedError

    @staticmethod
    def _is_valid_rate(value: Any) -> bool:
        """Проверить, что курс является положительным конечным числом."""
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value > 0
        )

    @staticmethod
    def _http_error_reason(status_code: int) -> str:
        """Вернуть понятное описание HTTP-ошибки."""
        if status_code in (401, 403):
            return (
                f"API отклонил запрос (HTTP {status_code}). "
                "Проверьте ключ и права доступа."
            )

        if status_code == 429:
            return "Превышен лимит запросов к API (HTTP 429)."

        if status_code >= 500:
            return f"Внешний API временно недоступен (HTTP {status_code})."

        return f"Ошибка HTTP при обращении к API: {status_code}."

    def _get_json(
        self,
        url: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Выполнить GET-запрос и получить JSON-ответ."""
        started_at = time.perf_counter()

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
            )

            if response.status_code != 200:
                reason = self._http_error_reason(response.status_code)
                logger.error("%s: %s", self.__class__.__name__, reason)
                raise ApiRequestError(reason)

            try:
                payload = response.json()
            except ValueError as error:
                reason = "Внешний API вернул некорректный JSON."
                logger.error("%s: %s", self.__class__.__name__, reason)
                raise ApiRequestError(reason) from error

            if not isinstance(payload, dict):
                raise ApiRequestError(
                    "Внешний API вернул данные в неожиданном формате."
                )

            elapsed = time.perf_counter() - started_at

            logger.debug(
                "%s: запрос выполнен за %.3f секунды.",
                self.__class__.__name__,
                elapsed,
            )

            return payload

        except requests.Timeout as error:
            reason = f"Превышено время ожидания запроса ({self.timeout} секунд)."
            logger.error("%s: %s", self.__class__.__name__, reason)
            raise ApiRequestError(reason) from error

        except requests.ConnectionError as error:
            reason = "Не удалось установить соединение с внешним API."
            logger.error("%s: %s", self.__class__.__name__, reason)
            raise ApiRequestError(reason) from error

        except requests.RequestException as error:
            reason = f"Ошибка HTTP-запроса: {error.__class__.__name__}."
            logger.error("%s: %s", self.__class__.__name__, reason)
            raise ApiRequestError(reason) from error


class CoinGeckoClient(BaseApiClient):
    """Клиент для получения курсов криптовалют через CoinGecko."""

    def fetch_rates(self) -> dict[str, float]:
        """Получить курсы криптовалют относительно базовой валюты."""
        url = f"{COINGECKO_BASE_URL}/simple/price"

        params = {
            "ids": ",".join(CRYPTO_ID_MAP.values()),
            "vs_currencies": BASE_CURRENCY.lower(),
        }

        payload = self._get_json(url, params)

        rates: dict[str, float] = {}

        for code, coin_id in CRYPTO_ID_MAP.items():
            coin_data = payload.get(coin_id)

            if not isinstance(coin_data, dict):
                logger.warning(
                    "CoinGecko не вернул данные для валюты %s.",
                    code,
                )
                continue

            rate = coin_data.get(BASE_CURRENCY.lower())

            if not self._is_valid_rate(rate):
                logger.warning(
                    "CoinGecko вернул некорректный курс для валюты %s.",
                    code,
                )
                continue

            rates[f"{code}_{BASE_CURRENCY}"] = float(rate)

        if not rates:
            raise ApiRequestError("CoinGecko не вернул ни одного корректного курса.")

        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Клиент для получения курсов фиатных валют через ExchangeRate-API."""

    def __init__(
        self,
        api_key: str | None = EXCHANGE_RATE_API_KEY,
        timeout: float = API_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        super().__init__(timeout, session)
        self.api_key = api_key

    def fetch_rates(self) -> dict[str, float]:
        """Получить курсы фиатных валют относительно базовой валюты."""
        if not self.api_key:
            raise ApiRequestError(
                "Не задан ключ доступа ExchangeRate-API. "
                "Установите переменную EXCHANGE_RATE_API_KEY."
            )

        encoded_key = quote(self.api_key, safe="")

        url = f"{EXCHANGE_RATE_API_BASE_URL}/{encoded_key}/latest/{BASE_CURRENCY}"

        payload = self._get_json(url)

        if payload.get("result") != "success":
            error_type = payload.get("error-type", "unknown")

            error_messages = {
                "invalid-key": "Неверный ключ API.",
                "inactive-account": "Аккаунт API не активирован.",
                "quota-reached": "Превышен лимит запросов API.",
                "unsupported-code": "Неподдерживаемый код базовой валюты.",
            }

            reason = error_messages.get(
                error_type,
                f"Ошибка ExchangeRate-API: {error_type}.",
            )

            raise ApiRequestError(reason)

        response_base = payload.get("base_code")

        if response_base != BASE_CURRENCY:
            raise ApiRequestError(
                "ExchangeRate-API вернул данные с неожиданной базовой валютой."
            )

        conversion_rates = payload.get("conversion_rates")

        if not isinstance(conversion_rates, dict):
            raise ApiRequestError("ExchangeRate-API не вернул таблицу курсов.")

        rates: dict[str, float] = {}

        for code in SUPPORTED_FIAT_CURRENCIES:
            if code == BASE_CURRENCY:
                continue

            direct_rate = conversion_rates.get(code)

            if not self._is_valid_rate(direct_rate):
                logger.warning(
                    "ExchangeRate-API не вернул корректный курс для валюты %s.",
                    code,
                )
                continue

            # API возвращает курс БАЗОВАЯ_ВАЛЮТА -> КОД.
            # В хранилище сохраняем обратный курс КОД -> БАЗОВАЯ_ВАЛЮТА.
            # Округление выполняется только при отображении результата.
            rates[f"{code}_{BASE_CURRENCY}"] = 1.0 / float(direct_rate)

        if not rates:
            raise ApiRequestError(
                "ExchangeRate-API не вернул ни одного корректного курса."
            )

        return rates
