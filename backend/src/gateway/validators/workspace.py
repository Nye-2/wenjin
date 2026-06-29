"""Workspace validators for workspace-related endpoints.

This module provides Pydantic models for validating workspace
creation, update, and query parameters.
"""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import sanitize_html, sanitize_string, validate_uuid


class WorkspaceType(StrEnum):
    """Valid workspace types."""

    SCI = "sci"
    THESIS = "thesis"
    PROPOSAL = "proposal"
    SOFTWARE_COPYRIGHT = "software_copyright"
    MATH_MODELING = "math_modeling"
    PATENT = "patent"


class WorkspaceStatus(StrEnum):
    """Valid workspace status values."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class CreateWorkspaceValidator(BaseModel):
    """Validator for workspace creation requests."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=255)]
    type: WorkspaceType
    discipline: Annotated[str, Field(max_length=100)] | None = None
    description: Annotated[str, Field(max_length=2000)] | None = None
    config: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        """Sanitize workspace name."""
        sanitized = sanitize_string(v, max_length=255)
        if not sanitized:
            raise ValueError("Workspace name cannot be empty or whitespace only")
        return sanitize_html(sanitized)

    @field_validator("discipline")
    @classmethod
    def sanitize_discipline(cls, v: str | None) -> str | None:
        """Sanitize discipline field."""
        if v is None:
            return None
        return sanitize_html(sanitize_string(v, max_length=100))

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: str | None) -> str | None:
        """Sanitize description field."""
        if v is None:
            return None
        return sanitize_html(sanitize_string(v, max_length=2000))

    @field_validator("config")
    @classmethod
    def validate_config(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        """Validate config dictionary."""
        if v is None:
            return None
        # Ensure config is a valid dict with string keys
        if not isinstance(v, dict):
            raise ValueError("Config must be a dictionary")
        return v


class UpdateWorkspaceValidator(BaseModel):
    """Validator for workspace update requests."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    discipline: Annotated[str, Field(max_length=100)] | None = None
    description: Annotated[str, Field(max_length=2000)] | None = None
    status: WorkspaceStatus | None = None
    config: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str | None) -> str | None:
        """Sanitize workspace name."""
        if v is None:
            return None
        sanitized = sanitize_string(v, max_length=255)
        if not sanitized:
            raise ValueError("Workspace name cannot be empty or whitespace only")
        return sanitize_html(sanitized)

    @field_validator("discipline")
    @classmethod
    def sanitize_discipline(cls, v: str | None) -> str | None:
        """Sanitize discipline field."""
        if v is None:
            return None
        return sanitize_html(sanitize_string(v, max_length=100))

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: str | None) -> str | None:
        """Sanitize description field."""
        if v is None:
            return None
        return sanitize_html(sanitize_string(v, max_length=2000))

    @field_validator("config")
    @classmethod
    def validate_config(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        """Validate config dictionary."""
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("Config must be a dictionary")
        return v


class WorkspaceIdValidator(BaseModel):
    """Validator for workspace ID path parameters."""

    workspace_id: str

    @field_validator("workspace_id")
    @classmethod
    def validate_workspace_id(cls, v: str) -> str:
        """Validate workspace ID is a valid UUID."""
        return validate_uuid(v)
