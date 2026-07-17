"""Conversation domain contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ConversationMessageCreateCommand(BaseModel):
    """Append one message to a thread conversation."""

    thread_id: str = Field(min_length=1, max_length=36)
    user_id: str = Field(min_length=1, max_length=36)
    workspace_id: str | None = Field(default=None, max_length=36)
    role: str = Field(min_length=1, max_length=32)
    content: str = ""
    sequence_index: int = Field(ge=0)
    timestamp: datetime | None = None
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_json: dict[str, Any] = Field(default_factory=dict)


class ConversationAttachmentStatePatchCommand(BaseModel):
    """Atomically patch one attachment task state inside a thread."""

    thread_id: str = Field(min_length=1, max_length=36)
    task_id: str = Field(min_length=1, max_length=100)
    state_key: Literal["extraction", "preprocess"]
    status: str = Field(min_length=1, max_length=50)
    state_patch: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    current_step: str | None = None
    error: str | None = None


class ConversationThreadCreateCommand(BaseModel):
    """Create one persisted conversation thread."""

    user_id: str = Field(min_length=1, max_length=36)
    workspace_id: str | None = Field(default=None, max_length=36)
    title: str | None = Field(default=None, max_length=255)
    model: str = Field(min_length=1, max_length=100)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConversationThreadUpdateCommand(BaseModel):
    """Patch mutable thread summary fields."""

    workspace_id: str | None = Field(default=None, max_length=36)
    title: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=100)
    message_count: int | None = Field(default=None, ge=0)
    last_message_preview: str | None = Field(default=None, max_length=255)
    last_message_role: str | None = Field(default=None, max_length=32)
    updated_at: datetime | None = None


class ConversationBlockRecord(BaseModel):
    """Canonical block projection."""

    id: str
    message_id: str
    thread_id: str
    block_type: str
    sequence_index: int
    payload_json: dict[str, Any] = Field(default_factory=dict)


class ConversationMessageRecord(BaseModel):
    """Canonical message projection."""

    id: str
    thread_id: str
    user_id: str
    workspace_id: str | None = None
    role: str
    content: str
    sequence_index: int
    timestamp: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    blocks: list[ConversationBlockRecord] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConversationThreadProjection(BaseModel):
    """Canonical thread summary projection for activity/history readers."""

    id: str
    user_id: str
    workspace_id: str | None = None
    title: str | None = None
    model: str | None = None
    workspace_type: str | None = None
    message_count: int = 0
    last_message_preview: str | None = None
    last_message_role: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
