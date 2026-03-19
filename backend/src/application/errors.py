"""Application-layer exceptions decoupled from HTTP transport."""


class ApplicationError(Exception):
    """Base application-layer error."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ApplicationError):
    """Requested resource was not found."""


class AccessDeniedError(ApplicationError):
    """Caller does not have permission for the operation."""


class BadRequestError(ApplicationError):
    """Request is invalid for business reasons."""


class ConflictError(ApplicationError):
    """Request conflicts with current state."""


class PaymentRequiredError(ApplicationError):
    """Request requires credits/payment."""


class TooManyRequestsError(ApplicationError):
    """Request exceeds concurrency or rate constraints."""


class InternalServiceError(ApplicationError):
    """Internal orchestration or queueing failure."""
