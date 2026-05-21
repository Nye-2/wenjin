"""Workspace template contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkspaceTemplatePayload(BaseModel):
    id: str
    workspace_id: str
    name: str
    category: str
    source_type: str
    source_file_path: str | None = None
    structure: dict[str, Any] = Field(default_factory=dict)
    format_spec: dict[str, Any] = Field(default_factory=dict)
    content_guidelines: dict[str, Any] = Field(default_factory=dict)
    latex_preamble: str | None = None
    is_active: bool
    is_builtin: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkspaceTemplateCreatePayload(BaseModel):
    workspace_id: str
    name: str
    category: str
    source_type: str
    source_file_path: str | None = None
    structure: dict[str, Any] = Field(default_factory=dict)
    format_spec: dict[str, Any] = Field(default_factory=dict)
    content_guidelines: dict[str, Any] = Field(default_factory=dict)
    latex_preamble: str | None = None


class WorkspaceTemplateDeactivatePayload(BaseModel):
    exclude_template_id: str | None = None
