"""Workspace validators for workspace-related endpoints.

This module provides Pydantic models for validating workspace
creation, update, and query parameters.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import sanitize_html, sanitize_string, validate_uuid


class WorkspaceType(StrEnum):
    """Valid workspace types."""

    SCI = "sci"
    THESIS = "thesis"
    PROPOSAL = "proposal"
    SOFTWARE_COPYRIGHT = "software_copyright"
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
    config: dict | None = None

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
    def validate_config(cls, v: dict | None) -> dict | None:
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
    config: dict | None = None

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
    def validate_config(cls, v: dict | None) -> dict | None:
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


class AddPaperToWorkspaceValidator(BaseModel):
    """Validator for adding paper to workspace requests."""

    model_config = ConfigDict(str_strip_whitespace=True)

    notes: Annotated[str, Field(max_length=5000)] | None = None
    tags: list[str] | None = None
    is_primary: bool = False

    @field_validator("notes")
    @classmethod
    def sanitize_notes(cls, v: str | None) -> str | None:
        """Sanitize notes field."""
        if v is None:
            return None
        return sanitize_html(sanitize_string(v, max_length=5000))

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str] | None) -> list[str] | None:
        """Validate and sanitize tags."""
        if v is None:
            return None
        if len(v) > 20:
            raise ValueError("Cannot have more than 20 tags")
        # Sanitize each tag
        sanitized_tags = []
        for tag in v:
            sanitized = sanitize_html(sanitize_string(tag, max_length=50))
            if sanitized:
                sanitized_tags.append(sanitized)
        return sanitized_tags
