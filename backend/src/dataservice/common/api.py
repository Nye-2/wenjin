"""DataService HTTP response envelope helpers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ErrorPayload(BaseModel):
    """Structured error returned by DataService APIs."""

    code: str
    message: str
    detail: dict[str, Any] | None = None


class DataServiceEnvelope(BaseModel):
    """Stable API envelope used by non-health DataService endpoints."""

    status: Literal["ok", "error"]
    data: Any = None
    error: ErrorPayload | None = None
    trace_id: str | None = None


def envelope_ok(data: Any = None, *, trace_id: str | None = None) -> dict[str, Any]:
    """Build a success envelope."""
    return DataServiceEnvelope(status="ok", data=data, trace_id=trace_id).model_dump(exclude_none=True)


def envelope_error(
    *,
    code: str,
    message: str,
    detail: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Build an error envelope."""
    error = ErrorPayload(code=code, message=message, detail=detail)
    return DataServiceEnvelope(status="error", error=error, trace_id=trace_id).model_dump(exclude_none=True)
