"""Tests for rate limiting middleware activation."""

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

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    # Use memory backend (no Redis needed for tests)
    with patch("src.gateway.middleware.rate_limit.settings") as mock_settings:
        mock_settings.RATE_LIMIT_REQUESTS = requests_per_minute
        mock_settings.RATE_LIMIT_WINDOW = window_seconds
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

    def test_health_endpoint_excluded_from_rate_limit(self):
        app = _make_rate_limited_app(requests_per_minute=1)
        client = TestClient(app)

        # Exhaust limit
        resp = client.get("/test")
        assert resp.status_code == 200

        # Health should still work
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_rate_limit_headers_present(self):
        app = _make_rate_limited_app(requests_per_minute=10)
        client = TestClient(app)
        resp = client.get("/test")
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Window" in resp.headers
