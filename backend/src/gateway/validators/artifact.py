"""Artifact validators for artifact-related endpoints.

This module provides Pydantic models for validating artifact
creation, update, and query parameters.
"""

from enum import Enum
from typing import Optional, Annotated, Any

from pydantic import BaseModel, Field, field_validator, ConfigDict

from .common import sanitize_string, sanitize_html, validate_uuid


class ArtifactType(str, Enum):
    """Valid artifact types."""

    RESEARCH_IDEA = "research_idea"
    METHODOLOGY = "methodology"
    FRAMEWORK_OUTLINE = "framework_outline"
    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    LITERATURE_REVIEW = "literature_review"
    HYPOTHESIS = "hypothesis"
    RESULTS_ANALYSIS = "results_analysis"
    CONCLUSION = "conclusion"
    REFERENCES = "references"
    FIGURE = "figure"
    TABLE = "table"
    CODE_SNIPPET = "code_snippet"
    NOTE = "note"
    SUMMARY = "summary"
    OTHER = "other"


class ArtifactStatus(str, Enum):
    """Valid artifact status values."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    ARCHIVED = "archived"


class CreateArtifactValidator(BaseModel):
    """Validator for artifact creation requests."""

    model_config = ConfigDict(str_strip_whitespace=True)

    workspace_id: str
    type: ArtifactType
    title: Optional[Annotated[str, Field(max_length=500)]] = None
    content: dict[str, Any]
    created_by_skill: Optional[Annotated[str, Field(max_length=100)]] = None
    parent_artifact_id: Optional[str] = None

    @field_validator("workspace_id")
    @classmethod
    def validate_workspace_id(cls, v: str) -> str:
        """Validate workspace ID is a valid UUID."""
        return validate_uuid(v)

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: Optional[str]) -> Optional[str]:
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
    def sanitize_skill_name(cls, v: Optional[str]) -> Optional[str]:
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
    def validate_parent_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate parent artifact ID if provided."""
        if v is None:
            return None
        return validate_uuid(v)


class UpdateArtifactValidator(BaseModel):
    """Validator for artifact update requests."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Optional[Annotated[str, Field(max_length=500)]] = None
    content: Optional[dict[str, Any]] = None
    status: Optional[ArtifactStatus] = None

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize artifact title."""
        if v is None:
            return None
        sanitized = sanitize_string(v, max_length=500)
        if not sanitized:
            return None
        return sanitize_html(sanitized)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
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
    type: Optional[ArtifactType] = None
    status: Optional[ArtifactStatus] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

    @field_validator("workspace_id")
    @classmethod
    def validate_workspace_id(cls, v: str) -> str:
        """Validate workspace ID is a valid UUID."""
        return validate_uuid(v)
