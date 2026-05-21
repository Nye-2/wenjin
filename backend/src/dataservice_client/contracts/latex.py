"""LaTeX adapter contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LatexProjectPayload(BaseModel):
    id: str
    user_id: str
    name: str
    template_id: str | None = None
    main_file: str
    tags: list[str] = Field(default_factory=list)
    archived: bool
    trashed: bool
    trashed_at: datetime | None = None
    file_order: dict[str, Any] = Field(default_factory=dict)
    llm_config: dict[str, Any] | None = None
    workspace_id: str | None = None
    surface_role: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LatexTemplatePayload(BaseModel):
    id: str
    label: str
    main_file: str
    category: str
    description: str | None = None
    description_en: str | None = None
    tags: list[str] = Field(default_factory=list)
    author: str | None = None
    featured: bool
    template_path: str | None = None


class LatexCompileHistoryPayload(BaseModel):
    id: str
    project_id: str
    engine: str
    main_file: str
    status: int
    log: str | None = None
    pdf_path: str | None = None
    created_at: datetime | None = None


class LatexProjectCreatePayload(BaseModel):
    user_id: str
    name: str
    template_id: str | None = None


class LatexProjectUpdatePayload(BaseModel):
    name: str | None = None
    template_id: str | None = None
    main_file: str | None = None
    tags: list[str] | None = None
    archived: bool | None = None
    trashed: bool | None = None
    llm_config: dict[str, Any] | None = None
    file_order: dict[str, Any] | None = None


class LatexProjectTouchPayload(BaseModel):
    file_order: dict[str, Any] | None = None
    main_file: str | None = None
    llm_config: dict[str, Any] | None = None


class LatexProjectAttachWorkspacePayload(BaseModel):
    workspace_id: str


class LatexCompileHistoryCreatePayload(BaseModel):
    project_id: str
    engine: str
    main_file: str
    status: int
    log: str | None = None
    pdf_path: str | None = None
