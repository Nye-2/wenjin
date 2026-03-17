"""Unified HTTP client with connection pooling, retry, and logging."""

import logging
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class UpstreamError(Exception):
    """Raised when an upstream service call fails after all retries."""

    def __init__(self, service: str, message: str, status_code: int | None = None) -> None:
        self.service = service
        self.status_code = status_code
        super().__init__(f"[{service}] {message}")


def _is_retryable(exc: BaseException) -> bool:
    """Return True for errors that should trigger a retry."""
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500:
        return True
    return False


class ServiceHttpClient:
    """Shared async HTTP client with connection pooling, tenacity retry, and request logging.

    Usage::

        _http = ServiceHttpClient(service_name="arxiv", timeout=30.0)
        response = await _http.get("http://export.arxiv.org/api/query", params={...})
    """

    def __init__(
        self,
        service_name: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.service_name = service_name
        self._timeout = timeout
        self._max_retries = max_retries
        self._default_headers = headers or {}
        self._client: httpx.AsyncClient | None = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily create the underlying httpx.AsyncClient on first use."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers=self._default_headers,
                follow_redirects=True,
            )
        return self._client

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send a GET request with retry and logging."""
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send a POST request with retry and logging."""
        return await self._request("POST", url, **kwargs)

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Execute an HTTP request with tenacity retry wrapper."""

        @retry(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
            reraise=True,
        )
        async def _do() -> httpx.Response:
            client = self._ensure_client()
            t0 = time.monotonic()
            response = await client.request(method, url, **kwargs)
            elapsed = time.monotonic() - t0
            logger.debug("%s %s %s %.3fs", self.service_name, method, url, elapsed)
            # Raise for 5xx so tenacity can see it; 4xx passes through.
            if response.status_code >= 500:
                response.raise_for_status()
            return response

        try:
            return await _do()
        except httpx.HTTPStatusError as exc:
            raise UpstreamError(self.service_name, str(exc), status_code=exc.response.status_code) from exc
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as exc:
            raise UpstreamError(self.service_name, str(exc)) from exc

    async def close(self) -> None:
        """Close the underlying connection pool."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
