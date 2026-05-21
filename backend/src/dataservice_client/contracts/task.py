"""Task persistence contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TaskRecordPayload(BaseModel):
    id: str
    user_id: str
    task_type: str
    workspace_id: str | None = None
    feature_id: str | None = None
    thread_id: str | None = None
    execution_id: str | None = None
    action: str | None = None
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


class TaskRecordCreatePayload(BaseModel):
    task_id: str = Field(min_length=1, max_length=36)
    user_id: str = Field(min_length=1, max_length=36)
    task_type: str = Field(min_length=1, max_length=50)
    priority: int = Field(ge=1, le=10)
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskRecordCreateGuardedPayload(TaskRecordCreatePayload):
    concurrency_limit: int = Field(ge=1)
    active_statuses: list[str] = Field(default_factory=list)


class TaskRecordPatchPayload(BaseModel):
    status: str | None = Field(default=None, max_length=20)
    result: dict[str, Any] | None = None
    error: str | None = None
    runtime_state: dict[str, Any] | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TaskRecordStartedPayload(BaseModel):
    started_at: datetime


class TaskRecordRuntimeStatePayload(BaseModel):
    runtime_state: dict[str, Any] | None = None


class TaskRecordCompletedPayload(BaseModel):
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    completed_at: datetime
    progress: int
    message: str | None = None
    runtime_state: dict[str, Any] | None = None
