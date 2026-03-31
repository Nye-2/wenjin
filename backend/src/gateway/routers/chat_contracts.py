"""Contracts shared by the chat router."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.application.results import GeneratedChatReply

ReasoningEffort = Literal["minimal", "low", "medium", "high"]
ChatUploadKind = Literal["literature", "workspace_context", "transient"]


class ChatMessage(BaseModel):
    """A single chat message."""

    role: str
    content: str
    timestamp: datetime | None = None
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatAttachment(BaseModel):
    """Thread-scoped chat attachment metadata."""

    name: str
    path: str
    kind: ChatUploadKind = "transient"
    url: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    paper_id: str | None = None
    artifact_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    """Chat request."""

    message: str
    workspace_id: str | None = None
    thread_id: str | None = None
    model: str | None = None
    skill: str | None = None
    thinking_enabled: bool = False
    reasoning_effort: ReasoningEffort | None = None
    stream: bool = True
    attachments: list[ChatAttachment] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    """Chat response."""

    thread_id: str
    message: ChatMessage
    workspace_id: str | None = None
    skill: str | None = None


class ThreadCreate(BaseModel):
    """Thread creation request."""

    workspace_id: str | None = None
    title: str | None = None
    model: str | None = None
    skill: str | None = None


class ThreadResponse(BaseModel):
    """Thread response."""

    id: str
    workspace_id: str | None
    title: str | None
    model: str
    skill: str | None
    messages: list[ChatMessage]
    created_at: datetime
    updated_at: datetime


class ThreadSummaryResponse(BaseModel):
    """Thread summary used by history and restoration surfaces."""

    id: str
    workspace_id: str | None
    title: str | None
    model: str
    skill: str | None
    message_count: int = 0
    last_message_preview: str | None = None
    last_message_role: str | None = None
    created_at: datetime
    updated_at: datetime


class ThreadListResponse(BaseModel):
    """List wrapper for thread summaries."""

    threads: list[ThreadSummaryResponse]
    count: int


class ThreadAgentStatusResponse(BaseModel):
    """Execution status for a chat thread."""

    thread_id: str
    status: str
    current_skill: str | None = None
    subagent_count: int = 0
