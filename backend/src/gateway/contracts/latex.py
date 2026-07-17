"""LaTeX gateway contracts for project, file, and template operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LatexProjectResponse(BaseModel):
    """LaTeX project response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    template_id: str | None
    main_file: str
    tags: list[str]
    archived: bool
    trashed: bool
    trashed_at: datetime | None
    file_order: dict[str, list[str]]
    llm_config: dict[str, Any] | None
    workspace_id: str | None = None
    surface_role: str | None = None
    created_at: datetime
    updated_at: datetime


class LatexProjectListResponse(BaseModel):
    """List response for LaTeX projects."""

    projects: list[LatexProjectResponse]


class LatexCreateProjectRequest(BaseModel):
    """Create payload."""

    name: str = Field(min_length=1, max_length=255)
    template_id: str | None = Field(default=None, max_length=50)


class LatexUpdateProjectRequest(BaseModel):
    """Update payload."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    template_id: str | None = Field(default=None, max_length=50)
    main_file: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = None
    archived: bool | None = None
    trashed: bool | None = None
    file_order: dict[str, list[str]] | None = None


class LatexFileItem(BaseModel):
    """File tree item."""

    path: str
    type: Literal["file", "dir"]


class LatexTreeResponse(BaseModel):
    """Tree response."""

    items: list[LatexFileItem]
    file_order: dict[str, list[str]]


class LatexFileContentResponse(BaseModel):
    """Text file payload."""

    content: str


class LatexWriteFileRequest(BaseModel):
    """Write file payload."""

    path: str = Field(min_length=1)
    content: str = ""


class LatexCreateFolderRequest(BaseModel):
    """Create folder payload."""

    path: str = Field(min_length=1)


class LatexRenamePathRequest(BaseModel):
    """Rename payload."""

    from_path: str = Field(alias="from", min_length=1)
    to_path: str = Field(alias="to", min_length=1)


class LatexFileOrderRequest(BaseModel):
    """File order payload."""

    folder: str = ""
    order: list[str]


class LatexTemplateResponse(BaseModel):
    """Template payload."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    main_file: str
    category: str
    description: str | None
    description_en: str | None
    tags: list[str]
    author: str | None
    featured: bool
    template_path: str | None


class LatexTemplateListResponse(BaseModel):
    """Template list response."""

    templates: list[LatexTemplateResponse]


class LatexUploadResponse(BaseModel):
    """Upload response."""

    ok: bool = True
    files: list[str]
    folders: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


class LatexProtectedSectionRequest(BaseModel):
    """Protect a workspace-owned Prism file or section from direct agent overwrite."""

    path: str = Field(min_length=1)
    section_key: str | None = None
    scope: Literal["file", "section"] = "file"
    reason: str | None = None


class LatexProtectedSectionResponse(BaseModel):
    """Protection write response."""

    ok: bool = True
    protected: bool = True
    path: str
    section_key: str
    scope: Literal["file", "section"]
    reason: str | None = None
