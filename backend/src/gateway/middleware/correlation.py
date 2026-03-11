"""Correlation ID middleware for request tracing."""

import uuid
from contextvars import ContextVar
from typing import Callable

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

    # Store in context
    correlation_id_var.set(correlation_id)

    # Process request
    response = await call_next(request)

    # Add to response headers
    response.headers["X-Correlation-ID"] = correlation_id

    return response


def get_correlation_id() -> str | None:
    """Get current correlation ID from context.

    Returns:
        The correlation ID if set, None otherwise.
    """
    return correlation_id_var.get()
