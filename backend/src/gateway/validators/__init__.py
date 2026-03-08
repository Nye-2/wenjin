"""Validators module for input validation across gateway endpoints.

This module provides comprehensive input validation using Pydantic v2 patterns.
"""

from .common import (
    validate_uuid,
    validate_email,
    sanitize_html,
    validate_page_number,
    ObjectId,
    EmailStr,
    SanitizedStr,
    PositiveInt,
)
from .workspace import (
    WorkspaceType,
    WorkspaceStatus,
    CreateWorkspaceValidator,
    UpdateWorkspaceValidator,
)
from .paper import (
    PaperSource,
    CreatePaperValidator,
    UpdatePaperValidator,
    AuthorValidator,
)
from .artifact import (
    ArtifactType,
    ArtifactStatus,
    CreateArtifactValidator,
    UpdateArtifactValidator,
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
    # Paper validators
    "PaperSource",
    "CreatePaperValidator",
    "UpdatePaperValidator",
    "AuthorValidator",
    # Artifact validators
    "ArtifactType",
    "ArtifactStatus",
    "CreateArtifactValidator",
    "UpdateArtifactValidator",
]
