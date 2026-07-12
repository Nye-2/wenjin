"""Map application-layer exceptions to HTTP exceptions."""

from fastapi import HTTPException, status

from src.application.errors import (
    AccessDeniedError,
    ApplicationError,
    BadRequestError,
    InternalServiceError,
    NotFoundError,
    PaymentRequiredError,
    TooManyRequestsError,
)
from src.dataservice_client.errors import DataServiceClientError
from src.runtime.chat_turns import ChatTurnConflictError


def to_http_exception(error: ApplicationError | ChatTurnConflictError) -> HTTPException:
    """Convert an application-layer error into an HTTP exception."""
    if isinstance(error, NotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, AccessDeniedError):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(error, PaymentRequiredError):
        code = status.HTTP_402_PAYMENT_REQUIRED
    elif isinstance(error, ChatTurnConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(error, TooManyRequestsError):
        code = status.HTTP_429_TOO_MANY_REQUESTS
    elif isinstance(error, BadRequestError):
        code = status.HTTP_400_BAD_REQUEST
    elif isinstance(error, InternalServiceError):
        code = status.HTTP_500_INTERNAL_SERVER_ERROR
    else:
        code = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = error.message if isinstance(error, ApplicationError) else str(error)
    return HTTPException(status_code=code, detail=detail)


def dataservice_client_to_http_exception(error: DataServiceClientError) -> HTTPException:
    """Preserve DataService HTTP semantics at the gateway boundary."""
    status_code = error.status_code
    if status_code is None or status_code < 400 or status_code >= 600:
        status_code = status.HTTP_502_BAD_GATEWAY
    return HTTPException(status_code=status_code, detail=str(error))
