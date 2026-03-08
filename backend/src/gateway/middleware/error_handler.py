"""Centralized error handling middleware for AcademiaGPT."""

import logging
from typing import Callable

from fastapi import Request, status, FastAPI
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException

from src.gateway.exceptions import (
    AcademiaGPTException,
    map_exception_to_status,
)


logger = logging.getLogger(__name__)


async def academia_exception_handler(request: Request, exc: AcademiaGPTException) -> JSONResponse:
    """Handle all AcademiaGPT custom exceptions.

    Args:
        request: The FastAPI request object.
        exc: The AcademiaGPT exception that was raised.

    Returns:
        JSONResponse with error details.
    """
    status_code = map_exception_to_status(exc)

    logger.warning(
        "AcademiaGPT exception: %s - %s (path: %s)",
        exc.code,
        exc.message,
        request.url.path,
    )

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
            }
        }
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle FastAPI request validation errors.

    Args:
        request: The FastAPI request object.
        exc: The validation error that was raised.

    Returns:
        JSONResponse with validation error details.
    """
    logger.warning(
        "Validation error on %s: %s",
        request.url.path,
        exc.errors(),
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request data",
                "details": exc.errors(),
            }
        }
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTP exceptions.

    Args:
        request: The FastAPI request object.
        exc: The HTTP exception that was raised.

    Returns:
        JSONResponse with HTTP error details.
    """
    logger.warning(
        "HTTP exception %d on %s: %s",
        exc.status_code,
        request.url.path,
        exc.detail,
    )

    # Map common HTTP status codes to error codes
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
    }

    error_code = code_map.get(exc.status_code, "HTTP_ERROR")

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": error_code,
                "message": str(exc.detail),
            }
        }
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle any unhandled exceptions.

    Args:
        request: The FastAPI request object.
        exc: The exception that was raised.

    Returns:
        JSONResponse with generic error message.
    """
    logger.exception(
        "Unhandled exception on %s: %s",
        request.url.path,
        str(exc),
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
            }
        }
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all error handlers with the FastAPI application.

    Args:
        app: The FastAPI application instance.
    """
    app.add_exception_handler(AcademiaGPTException, academia_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    logger.info("Error handlers registered successfully")
