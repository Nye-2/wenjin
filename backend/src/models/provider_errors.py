"""Provider-neutral classification for model transport failures."""

from __future__ import annotations


def is_transient_model_error(exc: BaseException) -> bool:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and (status_code in {408, 409, 429} or status_code >= 500):
        return True
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    return type(exc).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "ConnectError",
        "ConnectTimeout",
        "PoolTimeout",
        "RateLimitError",
        "ReadError",
        "ReadTimeout",
    }


def is_rate_limit_error(exc: BaseException) -> bool:
    return getattr(exc, "status_code", None) == 429 or type(exc).__name__ == "RateLimitError"


__all__ = ["is_rate_limit_error", "is_transient_model_error"]
