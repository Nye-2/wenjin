"""Workspace validators for workspace-related endpoints.

This module provides Pydantic models for validating workspace
creation, update, and query parameters.
"""

from enum import Enum
from typing import Optional, Annotated

from pydantic import BaseModel, Field, field_validator, ConfigDict

from .common import sanitize_string, sanitize_html, validate_uuid


class WorkspaceType(str, Enum):
    """Valid workspace types."""

    SCI = "sci"
    THESIS = "thesis"
    PROPOSAL = "proposal"
    GRANT = "grant"
    LITERATURE_REVIEW = "literature_review"


class WorkspaceStatus(str, Enum):
    """Valid workspace status values."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class CreateWorkspaceValidator(BaseModel):
    """Validator for workspace creation requests."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=255)]
    type: WorkspaceType
    discipline: Optional[Annotated[str, Field(max_length=100)]] = None
    description: Optional[Annotated[str, Field(max_length=2000)]] = None
    config: Optional[dict] = None

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
    def sanitize_discipline(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize discipline field."""
        if v is None:
            return None
        return sanitize_html(sanitize_string(v, max_length=100))

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize description field."""
        if v is None:
            return None
        return sanitize_html(sanitize_string(v, max_length=2000))

    @field_validator("config")
    @classmethod
    def validate_config(cls, v: Optional[dict]) -> Optional[dict]:
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

    name: Optional[Annotated[str, Field(min_length=1, max_length=255)]] = None
    discipline: Optional[Annotated[str, Field(max_length=100)]] = None
    description: Optional[Annotated[str, Field(max_length=2000)]] = None
    config: Optional[dict] = None
    status: Optional[WorkspaceStatus] = None

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize workspace name."""
        if v is None:
            return None
        sanitized = sanitize_string(v, max_length=255)
        if not sanitized:
            raise ValueError("Workspace name cannot be empty or whitespace only")
        return sanitize_html(sanitized)

    @field_validator("discipline")
    @classmethod
    def sanitize_discipline(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize discipline field."""
        if v is None:
            return None
        return sanitize_html(sanitize_string(v, max_length=100))

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize description field."""
        if v is None:
            return None
        return sanitize_html(sanitize_string(v, max_length=2000))

    @field_validator("config")
    @classmethod
    def validate_config(cls, v: Optional[dict]) -> Optional[dict]:
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

    notes: Optional[Annotated[str, Field(max_length=5000)]] = None
    tags: Optional[list[str]] = None
    is_primary: bool = False

    @field_validator("notes")
    @classmethod
    def sanitize_notes(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize notes field."""
        if v is None:
            return None
        return sanitize_html(sanitize_string(v, max_length=5000))

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[list[str]]) -> Optional[list[str]]:
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
