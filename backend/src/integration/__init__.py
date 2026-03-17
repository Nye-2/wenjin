"""Integration layer — shared HTTP client utilities."""

from .http_client import ServiceHttpClient, UpstreamError

__all__ = ["ServiceHttpClient", "UpstreamError"]
