"""Contracts shared by thread management endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ThreadUploadKind = Literal["literature", "workspace_context", "transient"]


class ThreadMessage(BaseModel):
    """A single thread message."""

    role: str
    content: str
    timestamp: datetime | None = None
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ThreadAttachment(BaseModel):
    """Thread-scoped attachment metadata."""

    name: str
    path: str
    kind: ThreadUploadKind = "transient"
    url: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    reference_id: str | None = None
    artifact_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ThreadCreate(BaseModel):
    """Thread creation request."""

    workspace_id: str | None = None
    title: str | None = None
    model: str | None = None


class WorkspaceThreadEnsureRequest(BaseModel):
    """Ensure the canonical workspace thread exists."""

    model: str | None = None


class ThreadResponse(BaseModel):
    """Thread response."""

    id: str
    workspace_id: str | None
    title: str | None
    model: str
    messages: list[ThreadMessage]
    created_at: datetime
    updated_at: datetime


class ThreadSummaryResponse(BaseModel):
    """Thread summary used by history and restoration surfaces."""

    id: str
    workspace_id: str | None
    title: str | None
    model: str
    message_count: int = 0
    last_message_preview: str | None = None
    last_message_role: str | None = None
    created_at: datetime
    updated_at: datetime


class ThreadListResponse(BaseModel):
    """List wrapper for thread summaries."""

    threads: list[ThreadSummaryResponse]
    count: int
