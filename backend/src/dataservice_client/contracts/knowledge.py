"""Knowledge memory contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeMemoryPayload(BaseModel):
    id: str
    user_id: str
    category: str
    content: str
    confidence: float
    source: str | None = None
    workspace_context: str | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class KnowledgeMemoryCreatePayload(BaseModel):
    user_id: str
    category: str
    content: str
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    source: str | None = None
    workspace_context: str | None = None


class KnowledgeMemoryUpdatePayload(BaseModel):
    content: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_active: bool | None = None


class KnowledgeArchiveLowConfidencePayload(BaseModel):
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
