"""Centralized exception classes for Wenjin."""

from fastapi import status


class WenjinException(Exception):
    """Base exception for Wenjin."""

    def __init__(self, message: str, code: str = "UNKNOWN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class NotFoundError(WenjinException):
    """Resource not found."""

    def __init__(self, resource: str, identifier: str):
        super().__init__(
            f"{resource} with id '{identifier}' not found",
            code="NOT_FOUND"
        )


class ValidationError(WenjinException):
    """Validation failed."""

    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR")


class DuplicateError(WenjinException):
    """Duplicate resource."""

    def __init__(self, resource: str, field: str, value: str):
        super().__init__(
            f"{resource} with {field} '{value}' already exists",
            code="DUPLICATE"
        )


class AuthenticationError(WenjinException):
    """Authentication failed."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, code="AUTH_ERROR")


class AuthorizationError(WenjinException):
    """Authorization failed."""

    def __init__(self, message: str = "Not authorized"):
        super().__init__(message, code="FORBIDDEN")


class RateLimitError(WenjinException):
    """Rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, code="RATE_LIMIT_EXCEEDED")


class ServiceUnavailableError(WenjinException):
    """External service unavailable."""

    def __init__(self, service: str, message: str | None = None):
        error_message = message or f"{service} is currently unavailable"
        super().__init__(error_message, code="SERVICE_UNAVAILABLE")


# ============ Domain-Specific Exceptions ============

class LiteratureError(WenjinException):
    """Base exception for literature module."""

    pass


class ExternalAPIError(LiteratureError):
    """External API request failed."""

    def __init__(self, source: str, message: str):
        super().__init__(f"{source} API error: {message}", "EXTERNAL_API_ERROR")


class CitationError(WenjinException):
    """Base exception for citation module."""

    pass


class InvalidBibTeXError(CitationError):
    """Invalid BibTeX format."""

    def __init__(self, message: str):
        super().__init__(f"Invalid BibTeX: {message}", "INVALID_BIBTEX")


class ExecutionError(WenjinException):
    """Base exception for execution module."""

    pass


class DockerUnavailableError(ExecutionError):
    """Docker is not available."""

    def __init__(self):
        super().__init__("Docker is not available", "DOCKER_UNAVAILABLE")


class CompilationError(ExecutionError):
    """LaTeX compilation failed."""

    def __init__(self, message: str):
        super().__init__(f"Compilation failed: {message}", "COMPILATION_ERROR")


def map_exception_to_status(exc: WenjinException) -> int:
    """Map Wenjin exception to HTTP status code."""
    status_map = {
        "NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "VALIDATION_ERROR": status.HTTP_400_BAD_REQUEST,
        "DUPLICATE": status.HTTP_409_CONFLICT,
        "AUTH_ERROR": status.HTTP_401_UNAUTHORIZED,
        "FORBIDDEN": status.HTTP_403_FORBIDDEN,
        "RATE_LIMIT_EXCEEDED": status.HTTP_429_TOO_MANY_REQUESTS,
        "SERVICE_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
        "EXTERNAL_API_ERROR": status.HTTP_502_BAD_GATEWAY,
        "INVALID_BIBTEX": status.HTTP_400_BAD_REQUEST,
        "DOCKER_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
        "COMPILATION_ERROR": status.HTTP_422_UNPROCESSABLE_CONTENT,
    }
    return status_map.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
