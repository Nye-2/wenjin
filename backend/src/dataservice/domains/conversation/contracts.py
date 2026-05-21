"""Conversation domain contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

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


class ConversationMessagesRebuildCommand(BaseModel):
    """Replace canonical message/block rows from an API message list."""

    thread_id: str = Field(min_length=1, max_length=36)
    user_id: str = Field(min_length=1, max_length=36)
    workspace_id: str | None = Field(default=None, max_length=36)
    messages: list[dict[str, Any]] = Field(default_factory=list)


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
    skill: str | None = None
    message_count: int = 0
    last_message_preview: str | None = None
    last_message_role: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
