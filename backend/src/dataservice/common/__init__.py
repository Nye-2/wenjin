"""Shared DataService primitives."""

from .actor import ActorContext, ActorKind
from .api import DataServiceEnvelope, ErrorPayload, envelope_error, envelope_ok
from .errors import (
    DataServiceConflictError,
    DataServiceError,
    DataServiceForbiddenError,
    DataServiceIdempotencyConflictError,
    DataServiceNotFoundError,
    DataServiceUnauthenticatedInternalCallError,
    DataServiceValidationError,
)
from .idempotency import IdempotencyScope, make_request_hash, make_scope_hash
from .pagination import Page, PageRequest
from .unit_of_work import DataServiceUnitOfWork

__all__ = [
    "ActorContext",
    "ActorKind",
    "DataServiceConflictError",
    "DataServiceEnvelope",
    "DataServiceError",
    "DataServiceForbiddenError",
    "DataServiceIdempotencyConflictError",
    "DataServiceNotFoundError",
    "DataServiceUnauthenticatedInternalCallError",
    "DataServiceUnitOfWork",
    "DataServiceValidationError",
    "ErrorPayload",
    "IdempotencyScope",
    "Page",
    "PageRequest",
    "envelope_error",
    "envelope_ok",
    "make_request_hash",
    "make_scope_hash",
]
