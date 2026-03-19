"""Artifact validators for artifact-related endpoints.

This module provides Pydantic models for validating artifact
creation, update, and query parameters.
"""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.artifacts import ArtifactType

from .common import sanitize_html, sanitize_string, validate_uuid


class ArtifactStatus(StrEnum):
    """Valid artifact status values."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    ARCHIVED = "archived"


class ArtifactCreatePayloadValidator(BaseModel):
    """Shared validator for artifact creation payload fields."""

    model_config = ConfigDict(str_strip_whitespace=True)

    type: ArtifactType
    title: Annotated[str, Field(max_length=500)] | None = None
    content: dict[str, Any]
    created_by_skill: Annotated[str, Field(max_length=100)] | None = None
    parent_artifact_id: str | None = None

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: str | None) -> str | None:
        """Sanitize artifact title."""
        if v is None:
            return None
        sanitized = sanitize_string(v, max_length=500)
        if not sanitized:
            return None
        return sanitize_html(sanitized)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate content dictionary."""
        if not isinstance(v, dict):
            raise ValueError("Content must be a dictionary")
        if not v:
            raise ValueError("Content cannot be empty")
        return v

    @field_validator("created_by_skill")
    @classmethod
    def sanitize_skill_name(cls, v: str | None) -> str | None:
        """Sanitize skill name."""
        if v is None:
            return None
        # Allow only alphanumeric, underscore, and hyphen
        import re
        sanitized = sanitize_string(v, max_length=100)
        if sanitized and not re.match(r"^[a-zA-Z0-9_-]+$", sanitized):
            raise ValueError("Skill name can only contain alphanumeric characters, underscores, and hyphens")
        return sanitized

    @field_validator("parent_artifact_id")
    @classmethod
    def validate_parent_id(cls, v: str | None) -> str | None:
        """Validate parent artifact ID if provided."""
        if v is None:
            return None
        return validate_uuid(v)


class CreateArtifactValidator(ArtifactCreatePayloadValidator):
    """Validator for artifact creation requests."""

    workspace_id: str

    @field_validator("workspace_id")
    @classmethod
    def validate_workspace_id(cls, v: str) -> str:
        """Validate workspace ID is a valid UUID."""
        return validate_uuid(v)


class UpdateArtifactValidator(BaseModel):
    """Validator for artifact update requests."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Annotated[str, Field(max_length=500)] | None = None
    content: dict[str, Any] | None = None
    status: ArtifactStatus | None = None

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: str | None) -> str | None:
        """Sanitize artifact title."""
        if v is None:
            return None
        sanitized = sanitize_string(v, max_length=500)
        if not sanitized:
            return None
        return sanitize_html(sanitized)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        """Validate content dictionary."""
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("Content must be a dictionary")
        if not v:
            raise ValueError("Content cannot be empty")
        return v


class ArtifactIdValidator(BaseModel):
    """Validator for artifact ID path parameters."""

    artifact_id: str

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, v: str) -> str:
        """Validate artifact ID is a valid UUID."""
        return validate_uuid(v)


class ListArtifactsQueryValidator(BaseModel):
    """Validator for artifact list query parameters."""

    workspace_id: str
    type: ArtifactType | None = None
    status: ArtifactStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

    @field_validator("workspace_id")
    @classmethod
    def validate_workspace_id(cls, v: str) -> str:
        """Validate workspace ID is a valid UUID."""
        return validate_uuid(v)
