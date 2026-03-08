"""Gateway middleware package."""

from .error_handler import (
    academia_exception_handler,
    validation_exception_handler,
    http_exception_handler,
    generic_exception_handler,
    register_error_handlers,
)

__all__ = [
    "academia_exception_handler",
    "validation_exception_handler",
    "http_exception_handler",
    "generic_exception_handler",
    "register_error_handlers",
]
