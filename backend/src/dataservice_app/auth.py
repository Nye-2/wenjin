"""Internal authentication for DataService."""

from __future__ import annotations

from fastapi import Header

from src.config import dataservice_settings
from src.dataservice.common.errors import DataServiceUnauthenticatedInternalCallError


async def require_internal_token(
    x_wenjin_internal_token: str | None = Header(default=None, alias="X-Wenjin-Internal-Token"),
) -> None:
    """Require the shared internal service token for non-health endpoints."""
    expected = dataservice_settings.internal_token
    if expected and x_wenjin_internal_token == expected:
        return
    raise DataServiceUnauthenticatedInternalCallError("Invalid DataService internal token")
