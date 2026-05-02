"""Correlation ID middleware for request tracing."""

import uuid
from typing import Any
from collections.abc import Callable
from contextvars import ContextVar

from fastapi import Request, Response

# Context variable for correlation ID
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


async def correlation_middleware(request: Request, call_next: Callable) -> Response:
    """Add correlation ID to all requests.

    Args:
        request: The incoming request.
        call_next: The next middleware/handler.

    Returns:
        The response with correlation ID header.
    """
    # Get or generate correlation ID
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

    # Store in context and restore previous value after the request completes.
    token = correlation_id_var.set(correlation_id)

    try:
        import sentry_sdk
        sentry_sdk.set_tag("correlation_id", correlation_id)
    except Exception:
        pass

    try:
        # Process request
        response = await call_next(request)

        # Add to response headers
        response.headers["X-Correlation-ID"] = correlation_id
        return response
    finally:
        correlation_id_var.reset(token)


def get_correlation_id() -> str | None:
    """Get current correlation ID from context.

    Returns:
        The correlation ID if set, None otherwise.
    """
    return correlation_id_var.get()
