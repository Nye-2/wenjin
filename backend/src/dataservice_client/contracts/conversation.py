"""Conversation contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ConversationBlockPayload(BaseModel):
    """Canonical conversation block payload."""

    id: str
    message_id: str
    thread_id: str
    block_type: str
    sequence_index: int
    payload_json: dict[str, Any] = Field(default_factory=dict)


class ConversationMessagePayload(BaseModel):
    """Canonical conversation message payload."""

    id: str
    thread_id: str
    user_id: str
    workspace_id: str | None = None
    role: str
    content: str
    sequence_index: int
    timestamp: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    blocks: list[ConversationBlockPayload] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConversationMessageCreatePayload(BaseModel):
    """Client-facing append-message payload."""

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


class ConversationMessagesRebuildPayload(BaseModel):
    """Client-facing rebuild-message payload."""

    thread_id: str = Field(min_length=1, max_length=36)
    user_id: str = Field(min_length=1, max_length=36)
    workspace_id: str | None = Field(default=None, max_length=36)
    messages: list[dict[str, Any]] = Field(default_factory=list)


class ConversationThreadCreatePayload(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    workspace_id: str | None = Field(default=None, max_length=36)
    title: str | None = Field(default=None, max_length=255)
    model: str = Field(min_length=1, max_length=100)
    skill: str | None = Field(default=None, max_length=100)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConversationThreadUpdatePayload(BaseModel):
    workspace_id: str | None = Field(default=None, max_length=36)
    title: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=100)
    skill: str | None = Field(default=None, max_length=100)
    message_count: int | None = Field(default=None, ge=0)
    last_message_preview: str | None = Field(default=None, max_length=255)
    last_message_role: str | None = Field(default=None, max_length=32)
    updated_at: datetime | None = None


class ConversationThreadPayload(BaseModel):
    id: str
    user_id: str
    workspace_id: str | None = None
    title: str | None = None
    model: str | None = None
    skill: str | None = None
    skill_name: str | None = None
    workspace_type: str | None = None
    message_count: int = 0
    last_message_preview: str | None = None
    last_message_role: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
