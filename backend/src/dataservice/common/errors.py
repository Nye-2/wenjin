"""Typed DataService errors."""

from __future__ import annotations

from typing import Any


class DataServiceError(Exception):
    """Base error carrying stable API error metadata."""

    code = "INTERNAL_ERROR"
    http_status = 500

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class DataServiceValidationError(DataServiceError):
    code = "VALIDATION_ERROR"
    http_status = 422


class DataServiceUnauthenticatedInternalCallError(DataServiceError):
    code = "UNAUTHENTICATED_INTERNAL_CALL"
    http_status = 401


class DataServiceForbiddenError(DataServiceError):
    code = "FORBIDDEN_WORKSPACE_ACCESS"
    http_status = 403


class DataServiceNotFoundError(DataServiceError):
    code = "NOT_FOUND"
    http_status = 404


class DataServiceConflictError(DataServiceError):
    code = "CONFLICT"
    http_status = 409


class DataServiceIdempotencyConflictError(DataServiceConflictError):
    code = "IDEMPOTENCY_CONFLICT"
