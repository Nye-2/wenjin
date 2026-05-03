"""Validators module for input validation across gateway endpoints.

This module provides comprehensive input validation using Pydantic v2 patterns.
"""

from .artifact import (  # type: ignore[attr-defined]
    ArtifactCreatePayloadValidator,
    ArtifactStatus,
    ArtifactType,
    CreateArtifactValidator,
    UpdateArtifactValidator,
)
from .common import (
    EmailStr,
    ObjectId,
    PositiveInt,
    SanitizedStr,
    sanitize_html,
    validate_email,
    validate_page_number,
    validate_uuid,
)
from .workspace import (
    CreateWorkspaceValidator,
    UpdateWorkspaceValidator,
    WorkspaceStatus,
    WorkspaceType,
)

__all__ = [
    # Common validators
    "validate_uuid",
    "validate_email",
    "sanitize_html",
    "validate_page_number",
    "ObjectId",
    "EmailStr",
    "SanitizedStr",
    "PositiveInt",
    # Workspace validators
    "WorkspaceType",
    "WorkspaceStatus",
    "CreateWorkspaceValidator",
    "UpdateWorkspaceValidator",
    # Artifact validators
    "ArtifactType",
    "ArtifactStatus",
    "ArtifactCreatePayloadValidator",
    "CreateArtifactValidator",
    "UpdateArtifactValidator",
]
