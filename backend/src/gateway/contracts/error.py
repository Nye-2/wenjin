"""Unified error contract for API responses.

All error responses follow this envelope:

    {
        "error": {
            "code": "ERROR_CODE",
            "message": "Human-readable message"
        }
    }

This matches the format already used in gateway/middleware/error_handler.py.
"""

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Inner error detail."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Unified error response envelope."""

    error: ErrorDetail
