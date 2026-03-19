"""Map application-layer exceptions to HTTP exceptions."""

from fastapi import HTTPException, status

from src.application.errors import (
    AccessDeniedError,
    ApplicationError,
    BadRequestError,
    ConflictError,
    InternalServiceError,
    NotFoundError,
    PaymentRequiredError,
    TooManyRequestsError,
)


def to_http_exception(error: ApplicationError) -> HTTPException:
    """Convert an application-layer error into an HTTP exception."""
    if isinstance(error, NotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, AccessDeniedError):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(error, PaymentRequiredError):
        code = status.HTTP_402_PAYMENT_REQUIRED
    elif isinstance(error, ConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(error, TooManyRequestsError):
        code = status.HTTP_429_TOO_MANY_REQUESTS
    elif isinstance(error, BadRequestError):
        code = status.HTTP_400_BAD_REQUEST
    elif isinstance(error, InternalServiceError):
        code = status.HTTP_500_INTERNAL_SERVER_ERROR
    else:
        code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return HTTPException(status_code=code, detail=error.message)
