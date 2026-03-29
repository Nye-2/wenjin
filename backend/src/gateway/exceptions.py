"""Centralized exception classes for Guanlan."""

from fastapi import status


class GuanlanException(Exception):
    """Base exception for Guanlan."""

    def __init__(self, message: str, code: str = "UNKNOWN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class NotFoundError(GuanlanException):
    """Resource not found."""

    def __init__(self, resource: str, identifier: str):
        super().__init__(
            f"{resource} with id '{identifier}' not found",
            code="NOT_FOUND"
        )


class ValidationError(GuanlanException):
    """Validation failed."""

    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR")


class DuplicateError(GuanlanException):
    """Duplicate resource."""

    def __init__(self, resource: str, field: str, value: str):
        super().__init__(
            f"{resource} with {field} '{value}' already exists",
            code="DUPLICATE"
        )


class AuthenticationError(GuanlanException):
    """Authentication failed."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, code="AUTH_ERROR")


class AuthorizationError(GuanlanException):
    """Authorization failed."""

    def __init__(self, message: str = "Not authorized"):
        super().__init__(message, code="FORBIDDEN")


class RateLimitError(GuanlanException):
    """Rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, code="RATE_LIMIT_EXCEEDED")


class ServiceUnavailableError(GuanlanException):
    """External service unavailable."""

    def __init__(self, service: str, message: str = None):
        error_message = message or f"{service} is currently unavailable"
        super().__init__(error_message, code="SERVICE_UNAVAILABLE")


# ============ Domain-Specific Exceptions ============

class LiteratureError(GuanlanException):
    """Base exception for literature module."""

    pass


class PaperNotFoundError(LiteratureError):
    """Paper not found in database or external source."""

    def __init__(self, paper_id: str):
        super().__init__(f"Paper not found: {paper_id}", "PAPER_NOT_FOUND")


class ExternalAPIError(LiteratureError):
    """External API request failed."""

    def __init__(self, source: str, message: str):
        super().__init__(f"{source} API error: {message}", "EXTERNAL_API_ERROR")


class CitationError(GuanlanException):
    """Base exception for citation module."""

    pass


class InvalidBibTeXError(CitationError):
    """Invalid BibTeX format."""

    def __init__(self, message: str):
        super().__init__(f"Invalid BibTeX: {message}", "INVALID_BIBTEX")


class ExecutionError(GuanlanException):
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


def map_exception_to_status(exc: GuanlanException) -> int:
    """Map Guanlan exception to HTTP status code."""
    status_map = {
        "NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "VALIDATION_ERROR": status.HTTP_400_BAD_REQUEST,
        "DUPLICATE": status.HTTP_409_CONFLICT,
        "AUTH_ERROR": status.HTTP_401_UNAUTHORIZED,
        "FORBIDDEN": status.HTTP_403_FORBIDDEN,
        "RATE_LIMIT_EXCEEDED": status.HTTP_429_TOO_MANY_REQUESTS,
        "SERVICE_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
        "PAPER_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "EXTERNAL_API_ERROR": status.HTTP_502_BAD_GATEWAY,
        "INVALID_BIBTEX": status.HTTP_400_BAD_REQUEST,
        "DOCKER_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
        "COMPILATION_ERROR": status.HTTP_422_UNPROCESSABLE_CONTENT,
    }
    return status_map.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
