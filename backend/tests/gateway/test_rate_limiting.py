"""Tests for rate limiting middleware activation."""

from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_rate_limited_app(requests_per_minute: int = 3, window_seconds: int = 60) -> FastAPI:
    """Create a minimal app with rate limiting enabled."""
    from src.gateway.middleware.rate_limit import setup_rate_limiting

    app = FastAPI()

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/readyz")
    async def readiness():
        return {"status": "healthy"}

    # Use memory backend (no Redis needed for tests)
    with patch("src.gateway.middleware.rate_limit.redis_settings") as mock_settings:
        mock_settings.rate_limit_requests = requests_per_minute
        mock_settings.rate_limit_window = window_seconds
        setup_rate_limiting(app, redis_client=None)

    return app


class TestRateLimiting:

    def test_requests_within_limit_succeed(self):
        app = _make_rate_limited_app(requests_per_minute=5)
        client = TestClient(app)
        for _ in range(5):
            resp = client.get("/test")
            assert resp.status_code == 200

    def test_requests_exceeding_limit_return_429(self):
        app = _make_rate_limited_app(requests_per_minute=3)
        client = TestClient(app)
        for _ in range(3):
            resp = client.get("/test")
            assert resp.status_code == 200

        resp = client.get("/test")
        assert resp.status_code == 429

    def test_readiness_endpoint_excluded_from_rate_limit(self):
        app = _make_rate_limited_app(requests_per_minute=1)
        client = TestClient(app)

        # Exhaust limit
        resp = client.get("/test")
        assert resp.status_code == 200

        # Health should still work
        resp = client.get("/readyz")
        assert resp.status_code == 200

    def test_rate_limit_headers_present(self):
        app = _make_rate_limited_app(requests_per_minute=10)
        client = TestClient(app)
        resp = client.get("/test")
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Window" in resp.headers

    def test_forwarded_for_is_ignored_for_untrusted_direct_client(self):
        from src.gateway.middleware.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(FastAPI())
        request = SimpleNamespace(
            headers={"X-Forwarded-For": "203.0.113.10"},
            client=SimpleNamespace(host="8.8.8.8"),
        )

        assert middleware._get_client_ip(request) == "8.8.8.8"

    def test_forwarded_for_is_used_for_private_proxy_hops(self):
        from src.gateway.middleware.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(FastAPI())
        request = SimpleNamespace(
            headers={"X-Forwarded-For": "203.0.113.10, 172.18.0.2"},
            client=SimpleNamespace(host="172.18.0.2"),
        )

        assert middleware._get_client_ip(request) == "203.0.113.10"

    @patch("time.time", side_effect=[100.0, 100.0, 100.0, 100.0])
    def test_redis_failure_falls_back_to_memory_limit(self, _mock_time):
        from src.gateway.middleware.rate_limit import RateLimitMiddleware

        class FailingRedis:
            @property
            def client(self):
                raise RuntimeError("redis unavailable")

        middleware = RateLimitMiddleware(
            FastAPI(),
            requests_per_minute=1,
            window_seconds=60,
            redis_client=FailingRedis(),
        )

        import asyncio

        assert asyncio.run(middleware._check_redis("rate_limit:test")) is True
        assert asyncio.run(middleware._check_redis("rate_limit:test")) is False

    def test_setup_uses_redis_settings_values(self):
        from src.gateway.middleware.rate_limit import RateLimitMiddleware, setup_rate_limiting

        app = FastAPI()
        with patch("src.gateway.middleware.rate_limit.redis_settings") as mock_settings:
            mock_settings.rate_limit_requests = 7
            mock_settings.rate_limit_window = 45
            setup_rate_limiting(app, redis_client=None)

        middleware = next(m for m in app.user_middleware if m.cls is RateLimitMiddleware)
        assert middleware.kwargs["requests_per_minute"] == 7
        assert middleware.kwargs["window_seconds"] == 45
