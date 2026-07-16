"""Rate limiting middleware for API protection.

This module provides rate limiting functionality using a sliding window
algorithm with Redis as the backend storage.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from ipaddress import ip_address
from typing import Protocol

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from src.config import redis_settings

logger = logging.getLogger(__name__)


class RedisPipelineProtocol(Protocol):
    """Minimal async Redis pipeline surface used by the middleware."""

    def zremrangebyscore(self, key: str, start: float | int, end: float | int) -> object: ...

    def zcard(self, key: str) -> object: ...

    def zadd(self, key: str, values: dict[str, float]) -> object: ...

    def expire(self, key: str, ttl_seconds: int) -> object: ...

    async def execute(self) -> list[object]: ...


class RedisBackendProtocol(Protocol):
    """Minimal Redis backend surface used by the middleware."""

    def pipeline(self) -> RedisPipelineProtocol: ...


RedisBackendProvider = Callable[[], RedisBackendProtocol]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using sliding window algorithm.

    Limits requests per IP address within a time window.
    Uses in-memory storage as fallback when Redis is not available.

    Attributes:
        requests_per_minute: Maximum requests allowed per minute
        window_seconds: Time window in seconds
        _storage: In-memory storage for rate limit counters
    """

    def __init__(
        self,
        app: ASGIApp,
        requests_per_minute: int = 60,
        window_seconds: int = 60,
        redis_backend_provider: RedisBackendProvider | None = None,
    ) -> None:
        """Initialize rate limiting middleware.

        Args:
            app: FastAPI application
            requests_per_minute: Maximum requests per minute (default: 60)
            window_seconds: Time window in seconds (default: 60)
            redis_backend_provider: Lazy provider for the connected Redis backend
        """
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self._redis_backend_provider = redis_backend_provider
        self._storage: dict[str, list[float]] = {}
        self._excluded_paths: set[str] = {
            "/livez",
            "/livez/",
            "/readyz",
            "/readyz/",
            "/docs",
            "/redoc",
            "/openapi.json",
        }
        # Upload and long-lived stream routes should not share the same bucket
        # as ordinary REST reads/writes, otherwise routine UI traffic can starve
        # user-initiated uploads or stream reconnects.
        self._bucket_limits: dict[str, tuple[int, int]] = {
            "default": (requests_per_minute, window_seconds),
            "uploads": (max(requests_per_minute, 60), window_seconds),
            "streams": (max(requests_per_minute * 4, 240), window_seconds),
        }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request through rate limiter.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response from handler or rate limit error
        """
        # Skip rate limiting for excluded paths
        if request.url.path in self._excluded_paths:
            return await call_next(request)

        # Skip for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Get client IP
        client_ip = self._get_client_ip(request)
        if not client_ip:
            return await call_next(request)

        # Check rate limit
        bucket = self._resolve_bucket(request.url.path)
        bucket_limit, bucket_window = self._bucket_limits.get(
            bucket,
            self._bucket_limits["default"],
        )
        key = f"rate_limit:{bucket}:{client_ip}"

        if self._redis_backend_provider is not None:
            allowed = await self._check_redis(
                key,
                requests_per_window=bucket_limit,
                window_seconds=bucket_window,
            )
        else:
            allowed = self._check_memory(
                key,
                requests_per_window=bucket_limit,
                window_seconds=bucket_window,
            )

        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded. Maximum {bucket_limit} requests per {bucket_window} seconds for {bucket} traffic.",
                    }
                },
                headers={
                    "X-RateLimit-Bucket": bucket,
                    "X-RateLimit-Limit": str(bucket_limit),
                    "X-RateLimit-Window": str(bucket_window),
                    "Retry-After": str(bucket_window),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Bucket"] = bucket
        response.headers["X-RateLimit-Limit"] = str(bucket_limit)
        response.headers["X-RateLimit-Window"] = str(bucket_window)

        return response

    @staticmethod
    def _resolve_bucket(path: str) -> str:
        normalized = (path or "").strip()
        if normalized == "/api":
            normalized = "/"
        elif normalized.startswith("/api/"):
            normalized = normalized[4:]

        # Run architecture stream endpoints
        if normalized.startswith("/threads/") and "/runs/" in normalized and normalized.endswith("/stream"):
            return "streams"
        if normalized.startswith("/threads/") and "/runs/" in normalized and normalized.endswith("/join"):
            return "streams"

        if normalized.startswith("/workspaces/") and normalized.endswith("/events"):
            return "streams"
        if normalized.startswith("/tasks/") and normalized.endswith("/stream"):
            return "streams"
        if normalized.startswith("/threads/") and normalized.endswith("/uploads"):
            return "uploads"
        return "default"

    def _get_client_ip(self, request: Request) -> str | None:
        """Extract client IP from request.

        Trust X-Forwarded-For only when the immediate peer is an internal proxy.

        Args:
            request: Incoming request

        Returns:
            Client IP address or None
        """
        client_host = request.client.host if request.client else None

        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for and self._is_trusted_proxy(client_host):
            original_ip = forwarded_for.split(",")[0].strip()
            if self._is_valid_ip(original_ip):
                return original_ip

        if client_host:
            return client_host

        return None

    @staticmethod
    def _is_valid_ip(value: str | None) -> bool:
        if not value:
            return False
        try:
            ip_address(value)
            return True
        except ValueError:
            return False

    @classmethod
    def _is_trusted_proxy(cls, host: str | None) -> bool:
        if not cls._is_valid_ip(host):
            return False
        assert host is not None
        parsed = ip_address(host)
        return parsed.is_loopback or parsed.is_private or parsed.is_link_local

    def _resolve_redis_backend(self) -> RedisBackendProtocol | None:
        if self._redis_backend_provider is None:
            return None
        return self._redis_backend_provider()

    async def _check_redis(
        self,
        key: str,
        *,
        requests_per_window: int | None = None,
        window_seconds: int | None = None,
    ) -> bool:
        """Check rate limit using Redis.

        Uses sliding window algorithm with sorted sets.

        Args:
            key: Redis key for the rate limit counter

        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        try:
            backend = self._resolve_redis_backend()
            if backend is None:
                return self._check_memory(
                    key,
                    requests_per_window=requests_per_window,
                    window_seconds=window_seconds,
                )

            effective_limit = requests_per_window or self.requests_per_minute
            effective_window = window_seconds or self.window_seconds

            now = time.time()
            window_start = now - effective_window

            # Use Redis pipeline for atomic operations
            pipe = backend.pipeline()

            # Remove old entries
            pipe.zremrangebyscore(key, 0, window_start)

            # Count current entries
            pipe.zcard(key)

            # Add current request
            pipe.zadd(key, {str(now): now})

            # Set expiry
            pipe.expire(key, effective_window + 1)

            redis_timeout_seconds = getattr(
                redis_settings,
                "rate_limit_redis_timeout_seconds",
                0.25,
            )
            results = await asyncio.wait_for(
                pipe.execute(),
                timeout=redis_timeout_seconds,
            )
            current_count_raw = results[1] if len(results) > 1 else 0
            if not isinstance(current_count_raw, (int, float)):
                return self._check_memory(
                    key,
                    requests_per_window=requests_per_window,
                    window_seconds=window_seconds,
                )
            current_count = int(current_count_raw)

            return current_count < effective_limit
        except TimeoutError:
            logger.warning(
                "Rate limit Redis check timed out for key=%s, falling back to in-memory limiter",
                key,
            )
            return self._check_memory(
                key,
                requests_per_window=requests_per_window,
                window_seconds=window_seconds,
            )
        except Exception:
            return self._check_memory(
                key,
                requests_per_window=requests_per_window,
                window_seconds=window_seconds,
            )

    def _check_memory(
        self,
        key: str,
        *,
        requests_per_window: int | None = None,
        window_seconds: int | None = None,
    ) -> bool:
        """Check rate limit using in-memory storage.

        Uses sliding window algorithm with list of timestamps.

        Args:
            key: Storage key for the rate limit counter

        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        effective_limit = requests_per_window or self.requests_per_minute
        effective_window = window_seconds or self.window_seconds
        now = time.time()
        window_start = now - effective_window

        # Get or create entry
        if key not in self._storage:
            self._storage[key] = []

        # Remove old entries
        self._storage[key] = [ts for ts in self._storage[key] if ts > window_start]

        # Check limit
        if len(self._storage[key]) >= effective_limit:
            return False

        # Add current request
        self._storage[key].append(now)

        return True


def setup_rate_limiting(
    app: FastAPI,
    redis_backend_provider: RedisBackendProvider | None = None,
) -> None:
    """Setup rate limiting middleware for a FastAPI app.

    Args:
        app: FastAPI application
        redis_backend_provider: Lazy provider for the connected Redis backend

    Usage:
        from src.gateway.middleware.rate_limit import setup_rate_limiting

        app = FastAPI()
        setup_rate_limiting(app, redis_backend_provider=lambda: my_redis_client)
    """
    # Get settings from config
    requests_per_minute = getattr(redis_settings, "rate_limit_requests", 60)
    window_seconds = getattr(redis_settings, "rate_limit_window", 60)

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=requests_per_minute,
        window_seconds=window_seconds,
        redis_backend_provider=redis_backend_provider,
    )
