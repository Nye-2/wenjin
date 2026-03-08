"""Common validation utilities and types.

This module provides reusable validation functions and custom types
for input validation across the gateway.
"""

import html
import re
from typing import Annotated

from pydantic import BeforeValidator, Field


def validate_uuid(value: str) -> str:
    """Validate UUID format.

    Args:
        value: String to validate as UUID

    Returns:
        Lowercase UUID string

    Raises:
        ValueError: If value is not a valid UUID format
    """
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    if not uuid_pattern.match(value):
        raise ValueError("Invalid UUID format")
    return value.lower()


def validate_email(value: str) -> str:
    """Validate and normalize email address.

    Args:
        value: Email string to validate

    Returns:
        Normalized (lowercase) email string

    Raises:
        ValueError: If email format is invalid
    """
    # Basic email regex pattern
    email_pattern = re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    )
    if not email_pattern.match(value):
        raise ValueError("Invalid email format")
    return value.lower().strip()


def sanitize_html(value: str) -> str:
    """Remove HTML tags and escape HTML entities from string.

    This function removes potentially dangerous HTML content while
    preserving the text content.

    Args:
        value: String that may contain HTML

    Returns:
        Sanitized string with HTML removed and entities escaped
    """
    if not value:
        return value

    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", "", value)

    # Escape any remaining HTML entities
    clean = html.escape(clean)

    return clean.strip()


def validate_page_number(value: int) -> int:
    """Validate page number is positive.

    Args:
        value: Page number to validate

    Returns:
        Validated page number

    Raises:
        ValueError: If page number is not positive
    """
    if value < 1:
        raise ValueError("Page number must be positive")
    return value


def validate_limit(value: int, max_limit: int = 100) -> int:
    """Validate limit parameter for pagination.

    Args:
        value: Limit value to validate
        max_limit: Maximum allowed limit (default 100)

    Returns:
        Validated limit value

    Raises:
        ValueError: If limit is not within valid range
    """
    if value < 1:
        raise ValueError("Limit must be at least 1")
    if value > max_limit:
        raise ValueError(f"Limit cannot exceed {max_limit}")
    return value


def sanitize_string(value: str, max_length: int | None = None) -> str:
    """Sanitize string input by stripping whitespace and optionally truncating.

    Args:
        value: String to sanitize
        max_length: Optional maximum length (will truncate if exceeded)

    Returns:
        Sanitized string
    """
    if not value:
        return value

    sanitized = value.strip()

    if max_length is not None and len(sanitized) > max_length:
        sanitized = sanitized[:max_length]

    return sanitized


def validate_password_strength(password: str) -> str:
    """Validate password meets minimum strength requirements.

    Requirements:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit

    Args:
        password: Password string to validate

    Returns:
        Validated password string

    Raises:
        ValueError: If password doesn't meet requirements
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")

    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")

    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")

    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit")

    return password


# Custom Pydantic types using Annotated

ObjectId = Annotated[
    str,
    BeforeValidator(lambda v: validate_uuid(v) if isinstance(v, str) else v),
    Field(..., description="Valid UUID string"),
]

EmailStr = Annotated[
    str,
    BeforeValidator(lambda v: validate_email(v) if isinstance(v, str) else v),
    Field(..., description="Valid email address"),
]

SanitizedStr = Annotated[
    str,
    BeforeValidator(lambda v: sanitize_html(v) if isinstance(v, str) else v),
    Field(..., description="HTML-sanitized string"),
]

PositiveInt = Annotated[
    int,
    BeforeValidator(lambda v: validate_page_number(v) if isinstance(v, int) else v),
    Field(..., description="Positive integer", ge=1),
]
