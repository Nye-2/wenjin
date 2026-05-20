"""Workspace contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkspacePayload(BaseModel):
    """Canonical DataService workspace payload."""

    id: str
    created_by_user_id: str
    name: str
    workspace_type: str
    discipline: str | None = None
    description: str | None = None
    settings_json: dict[str, Any] = Field(default_factory=dict)
    active_thread_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkspaceCreatePayload(BaseModel):
    """Client-facing workspace create payload."""

    created_by_user_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=255)
    workspace_type: str
    discipline: str | None = Field(default=None, max_length=100)
    description: str | None = None
    settings_json: dict[str, Any] = Field(default_factory=dict)


class WorkspaceUpdatePayload(BaseModel):
    """Client-facing workspace update payload."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    workspace_type: str | None = None
    discipline: str | None = Field(default=None, max_length=100)
    description: str | None = None
    settings_json: dict[str, Any] | None = None
    active_thread_id: str | None = None
