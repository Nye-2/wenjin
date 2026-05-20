"""HTTP client for the standalone DataService."""

from .client import AsyncDataServiceClient
from .errors import DataServiceClientError

__all__ = ["AsyncDataServiceClient", "DataServiceClientError"]
