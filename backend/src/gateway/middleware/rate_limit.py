"""Rate limiting middleware for API protection.

This module provides rate limiting functionality using a sliding window
algorithm with Redis as the backend storage.
"""

import time
from collections.abc import Callable
from ipaddress import ip_address

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import redis_settings


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
        app,
        requests_per_minute: int = 60,
        window_seconds: int = 60,
        redis_client=None,
    ):
        """Initialize rate limiting middleware.

        Args:
            app: FastAPI application
            requests_per_minute: Maximum requests per minute (default: 60)
            window_seconds: Time window in seconds (default: 60)
            redis_client: Optional Redis client for distributed rate limiting
        """
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self._redis = redis_client
        self._storage: dict[str, list[float]] = {}
        self._excluded_paths = {
            "/livez",
            "/livez/",
            "/readyz",
            "/readyz/",
            "/docs",
            "/redoc",
            "/openapi.json",
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
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
        key = f"rate_limit:{client_ip}"

        if self._redis:
            allowed = await self._check_redis(key)
        else:
            allowed = self._check_memory(key)

        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per {self.window_seconds} seconds.",
                    }
                },
                headers={
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Window": str(self.window_seconds),
                    "Retry-After": str(self.window_seconds),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Window"] = str(self.window_seconds)

        return response

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
        parsed = ip_address(host)
        return parsed.is_loopback or parsed.is_private or parsed.is_link_local

    def _resolve_redis_backend(self):
        if self._redis is None:
            return None
        if hasattr(self._redis, "client"):
            return self._redis.client
        return self._redis

    async def _check_redis(self, key: str) -> bool:
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
                return self._check_memory(key)

            now = time.time()
            window_start = now - self.window_seconds

            # Use Redis pipeline for atomic operations
            pipe = backend.pipeline()

            # Remove old entries
            pipe.zremrangebyscore(key, 0, window_start)

            # Count current entries
            pipe.zcard(key)

            # Add current request
            pipe.zadd(key, {str(now): now})

            # Set expiry
            pipe.expire(key, self.window_seconds + 1)

            results = await pipe.execute()
            current_count = results[1]

            return current_count < self.requests_per_minute

        except Exception:
            return self._check_memory(key)

    def _check_memory(self, key: str) -> bool:
        """Check rate limit using in-memory storage.

        Uses sliding window algorithm with list of timestamps.

        Args:
            key: Storage key for the rate limit counter

        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Get or create entry
        if key not in self._storage:
            self._storage[key] = []

        # Remove old entries
        self._storage[key] = [
            ts for ts in self._storage[key] if ts > window_start
        ]

        # Check limit
        if len(self._storage[key]) >= self.requests_per_minute:
            return False

        # Add current request
        self._storage[key].append(now)

        return True


def setup_rate_limiting(app, redis_client=None):
    """Setup rate limiting middleware for a FastAPI app.

    Args:
        app: FastAPI application
        redis_client: Optional Redis client for distributed rate limiting

    Usage:
        from src.gateway.middleware.rate_limit import setup_rate_limiting

        app = FastAPI()
        setup_rate_limiting(app, redis_client=my_redis_client)
    """
    # Get settings from config
    requests_per_minute = getattr(redis_settings, "rate_limit_requests", 60)
    window_seconds = getattr(redis_settings, "rate_limit_window", 60)

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=requests_per_minute,
        window_seconds=window_seconds,
        redis_client=redis_client,
    )
