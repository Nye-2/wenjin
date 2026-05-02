"""LLM error handling middleware with retry hints and circuit breaker."""

from __future__ import annotations

import logging
import threading
import time
from email.utils import parsedate_to_datetime
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState
from src.config.config_loader import get_app_config

logger = logging.getLogger(__name__)

_RETRIABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
_BUSY_PATTERNS = (
    "server busy",
    "temporarily unavailable",
    "try again later",
    "please retry",
    "please try again",
    "overloaded",
    "high demand",
    "rate limit",
    "服务繁忙",
    "稍后重试",
    "请稍后重试",
)
_QUOTA_PATTERNS = (
    "insufficient_quota",
    "quota",
    "billing",
    "credit",
    "payment",
    "余额不足",
    "超出限额",
    "额度不足",
    "欠费",
)
_AUTH_PATTERNS = (
    "authentication",
    "unauthorized",
    "invalid api key",
    "invalid_api_key",
    "permission",
    "forbidden",
    "access denied",
    "无权",
    "未授权",
)


class LLMErrorHandlingMiddleware(Middleware):
    """Handle transient LLM failures and expose graceful fallback responses."""

    retry_max_attempts: int
    retry_base_delay_ms: int
    retry_cap_delay_ms: int
    circuit_failure_threshold: int
    circuit_recovery_timeout_sec: int

    def __init__(
        self,
        retry_max_attempts: int = 3,
        retry_base_delay_ms: int = 1000,
        retry_cap_delay_ms: int = 8000,
        circuit_failure_threshold: int = 5,
        circuit_recovery_timeout_sec: int = 60,
        *,
        load_from_app_config: bool = False,
    ) -> None:
        self.retry_max_attempts = retry_max_attempts
        self.retry_base_delay_ms = retry_base_delay_ms
        self.retry_cap_delay_ms = retry_cap_delay_ms

        self.circuit_failure_threshold = circuit_failure_threshold
        self.circuit_recovery_timeout_sec = circuit_recovery_timeout_sec

        if load_from_app_config:
            try:
                config = get_app_config()
                breaker = getattr(config, "circuit_breaker", None)
                if breaker is not None:
                    failure_threshold = getattr(breaker, "failure_threshold", None)
                    recovery_timeout_sec = getattr(breaker, "recovery_timeout_sec", None)
                    if isinstance(failure_threshold, int):
                        self.circuit_failure_threshold = failure_threshold
                    if isinstance(recovery_timeout_sec, int):
                        self.circuit_recovery_timeout_sec = recovery_timeout_sec
            except Exception:
                logger.debug("Failed to load circuit breaker config, falling back to defaults")

        self._circuit_lock = threading.Lock()
        self._circuit_failure_count = 0
        self._circuit_open_until = 0.0
        self._circuit_state = "closed"

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        if not self._check_circuit_open():
            return {}

        messages = list(state.get("messages", []))
        messages.append(AIMessage(content=self._build_circuit_breaker_message()))
        return {
            "messages": messages,
            "_skip_model_call": True,
        }

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        return {}

    async def on_model_error(
        self,
        state: ThreadState,
        config: RunnableConfig,
        error: Exception,
    ) -> dict[str, Any] | None:
        retriable, reason = self.classify_error(error)
        if not retriable and reason == "generic":
            return None

        messages = list(state.get("messages", []))
        messages.append(AIMessage(content=self._build_user_message(error, reason)))
        return {"messages": messages}

    def classify_error(self, error: BaseException) -> tuple[bool, str]:
        detail = _extract_error_detail(error).lower()
        error_code = str(_extract_error_code(error) or "").lower()
        status_code = _extract_status_code(error)
        exc_name = error.__class__.__name__

        if _matches_any(detail, _QUOTA_PATTERNS) or _matches_any(error_code, _QUOTA_PATTERNS):
            return False, "quota"
        if _matches_any(detail, _AUTH_PATTERNS):
            return False, "auth"

        if exc_name in {"APITimeoutError", "APIConnectionError", "InternalServerError"}:
            return True, "transient"
        if status_code in _RETRIABLE_STATUS_CODES:
            return True, "transient"
        if _matches_any(detail, _BUSY_PATTERNS):
            return True, "busy"

        return False, "generic"

    def build_retry_delay_ms(self, attempt: int, error: BaseException) -> int:
        retry_after_ms = _extract_retry_after_ms(error)
        if retry_after_ms is not None:
            return retry_after_ms
        backoff = self.retry_base_delay_ms * (2 ** max(0, attempt - 1))
        return int(min(backoff, self.retry_cap_delay_ms))

    def log_retry(self, attempt: int, wait_ms: int, reason: str, error: BaseException) -> None:
        logger.warning(
            "Transient LLM error (%s) on attempt %d/%d; retrying in %dms: %s",
            reason,
            attempt,
            self.retry_max_attempts,
            wait_ms,
            _extract_error_detail(error),
        )

    def should_passthrough(self, error: BaseException) -> bool:
        error_name = error.__class__.__name__
        return error_name in {
            "GraphRecursionError",
            "GraphBubbleUp",
            "CancelledError",
            "TimeoutError",
        }

    def record_success(self) -> None:
        with self._circuit_lock:
            self._circuit_failure_count = 0
            self._circuit_open_until = 0.0
            self._circuit_state = "closed"

    def record_failure(self) -> None:
        with self._circuit_lock:
            self._circuit_failure_count += 1
            if self._circuit_failure_count >= self.circuit_failure_threshold:
                self._circuit_state = "open"
                self._circuit_open_until = time.time() + self.circuit_recovery_timeout_sec
                logger.error(
                    "Circuit breaker tripped after %d consecutive failures. Recovery timeout=%ss",
                    self._circuit_failure_count,
                    self.circuit_recovery_timeout_sec,
                )

    def _check_circuit_open(self) -> bool:
        with self._circuit_lock:
            if self._circuit_state != "open":
                return False
            if time.time() < self._circuit_open_until:
                return True
            self._circuit_state = "closed"
            self._circuit_open_until = 0.0
            self._circuit_failure_count = 0
            return False

    @staticmethod
    def _build_circuit_breaker_message() -> str:
        return (
            "当前模型服务连续失败，已触发熔断保护。"
            "请稍后重试，或切换可用模型后继续。"
        )

    @staticmethod
    def _build_user_message(error: BaseException, reason: str) -> str:
        if reason == "quota":
            return "当前模型服务因额度/计费限制拒绝请求。请检查额度或切换模型后重试。"
        if reason == "auth":
            return "当前模型服务鉴权失败。请检查 API Key 或访问权限配置。"
        if reason in {"busy", "transient"}:
            return "当前模型服务暂时不可用（已重试仍失败）。请稍后再试。"
        return f"模型调用失败：{_extract_error_detail(error)}"


def _matches_any(detail: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in detail for pattern in patterns)


def _extract_error_detail(error: BaseException) -> str:
    for attr in ("message", "detail", "msg"):
        value = getattr(error, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    text = str(error).strip()
    return text or error.__class__.__name__


def _extract_error_code(error: BaseException) -> Any:
    for attr in ("code", "error_code"):
        value = getattr(error, attr, None)
        if value not in (None, ""):
            return value
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return err.get("code")
    return None


def _extract_status_code(error: BaseException) -> int | None:
    for attr in ("status_code", "status"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    return None


def _extract_retry_after_ms(error: BaseException) -> int | None:
    headers = getattr(error, "headers", None)
    if not isinstance(headers, dict):
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", None)
    if not isinstance(headers, dict):
        return None

    value = headers.get("Retry-After") or headers.get("retry-after")
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return max(0, int(float(value) * 1000))

    if isinstance(value, str):
        stripped = value.strip()
        if stripped.replace(".", "", 1).isdigit():
            return max(0, int(float(stripped) * 1000))
        try:
            dt = parsedate_to_datetime(stripped)
            delay = dt.timestamp() - time.time()
            return max(0, int(delay * 1000))
        except Exception:
            return None
    return None
