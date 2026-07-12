"""Task persistence contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TaskRecordCreateCommand(BaseModel):
    """Create one persistent task record."""

    task_id: str = Field(min_length=1, max_length=36)
    user_id: str = Field(min_length=1, max_length=36)
    task_type: str = Field(min_length=1, max_length=50)
    priority: int = Field(ge=1, le=10)
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="pending", max_length=20)


class TaskRecordPatchCommand(BaseModel):
    """Patch mutable task record state."""

    status: str | None = Field(default=None, max_length=20)
    result: dict[str, Any] | None = None
    error: str | None = None
    runtime_state: dict[str, Any] | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TaskRecordProjection(BaseModel):
    """DataService-owned task record projection."""

    id: str
    user_id: str
    task_type: str
    workspace_id: str | None = None
    thread_id: str | None = None
    mission_id: str | None = None
    status: str
    priority: int
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    runtime_state: dict[str, Any] | None = None
    progress: int = 0
    message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
