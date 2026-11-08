"""Декораторы для логирования доменных операций."""

import inspect
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)


def log_action(
    action: str,
    verbose: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Логировать результат доменной операции и пробрасывать исключения."""
    action_code = action.strip().upper()

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        signature = inspect.signature(func)

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            arguments = signature.bind(*args, **kwargs).arguments

            timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

            user_id = arguments.get("user_id")
            currency_code = arguments.get("currency_code")
            amount = arguments.get("amount")

            context = (
                f"timestamp={timestamp} "
                f"action={action_code} "
                f"user_id={user_id!r} "
                f"currency_code={currency_code!r} "
                f"amount={amount!r}"
            )

            try:
                result = func(*args, **kwargs)
            except Exception as error:
                logger.info(
                    "%s rate=None base='USD' result=ERROR "
                    "error_type=%s error_message=%r",
                    context,
                    type(error).__name__,
                    str(error),
                )
                raise

            rate = None
            balance_details = ""

            if isinstance(result, dict):
                rate = result.get("rate_usd")

                if verbose:
                    balance_after = result.get("balance")
                    operation_amount = result.get("amount")

                    if isinstance(balance_after, (int, float)) and isinstance(
                        operation_amount, (int, float)
                    ):
                        if action_code == "BUY":
                            balance_before = balance_after - operation_amount
                        elif action_code == "SELL":
                            balance_before = balance_after + operation_amount
                        else:
                            balance_before = None

                        if balance_before is not None:
                            balance_details = (
                                f" balance_before={balance_before:.8f}"
                                f" balance_after={balance_after:.8f}"
                            )

            logger.info(
                "%s rate=%r base='USD' result=OK%s",
                context,
                rate,
                balance_details,
            )

            return result

        return wrapper

    return decorator
