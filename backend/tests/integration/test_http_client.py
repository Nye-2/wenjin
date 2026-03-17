"""Tests for ServiceHttpClient."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.integration.http_client import ServiceHttpClient, UpstreamError


@pytest.fixture
def svc():
    """Create a ServiceHttpClient for testing."""
    return ServiceHttpClient(service_name="test_svc", timeout=5.0, max_retries=2)


class TestServiceHttpClient:
    """Unit tests for ServiceHttpClient."""

    @pytest.mark.asyncio
    async def test_get_success(self, svc):
        """Successful GET returns response."""
        mock_response = httpx.Response(200, text="ok")
        with patch.object(svc, "_ensure_client") as mock_ensure:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_ensure.return_value = mock_client

            resp = await svc.get("https://example.com/api")

            assert resp.status_code == 200
            mock_client.request.assert_awaited_once_with("GET", "https://example.com/api")

    @pytest.mark.asyncio
    async def test_post_success(self, svc):
        """Successful POST returns response."""
        mock_response = httpx.Response(200, json={"id": 1})
        with patch.object(svc, "_ensure_client") as mock_ensure:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_ensure.return_value = mock_client

            resp = await svc.post("https://example.com/api", json={"key": "val"})

            assert resp.status_code == 200
            mock_client.request.assert_awaited_once_with("POST", "https://example.com/api", json={"key": "val"})

    @pytest.mark.asyncio
    async def test_4xx_not_retried(self, svc):
        """4xx responses are returned directly (not retried)."""
        mock_response = httpx.Response(404, text="not found")
        with patch.object(svc, "_ensure_client") as mock_ensure:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_ensure.return_value = mock_client

            resp = await svc.get("https://example.com/missing")

            assert resp.status_code == 404
            # Should be called only once (no retry)
            assert mock_client.request.await_count == 1

    @pytest.mark.asyncio
    async def test_5xx_retried_then_upstream_error(self, svc):
        """5xx triggers retries and eventually raises UpstreamError."""
        request = httpx.Request("GET", "https://example.com/fail")
        mock_response = httpx.Response(503, request=request)
        with patch.object(svc, "_ensure_client") as mock_ensure:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_ensure.return_value = mock_client

            with pytest.raises(UpstreamError) as exc_info:
                await svc.get("https://example.com/fail")

            assert exc_info.value.service == "test_svc"
            assert exc_info.value.status_code == 503
            # max_retries=2, so should be called twice
            assert mock_client.request.await_count == 2

    @pytest.mark.asyncio
    async def test_connection_error_retried_then_upstream_error(self, svc):
        """Connection errors trigger retries and eventually raise UpstreamError."""
        with patch.object(svc, "_ensure_client") as mock_ensure:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.ConnectError("connection refused")
            mock_ensure.return_value = mock_client

            with pytest.raises(UpstreamError) as exc_info:
                await svc.get("https://example.com/down")

            assert exc_info.value.service == "test_svc"
            assert exc_info.value.status_code is None
            assert mock_client.request.await_count == 2

    @pytest.mark.asyncio
    async def test_lazy_client_creation(self, svc):
        """Client is not created until first request."""
        assert svc._client is None
        # After _ensure_client, client exists
        client = svc._ensure_client()
        assert client is not None
        assert svc._client is client
        await svc.close()
        assert svc._client is None
