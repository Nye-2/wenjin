"""Audit contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditLogCreatePayload(BaseModel):
    action: str
    user_id: str | None = None
    workspace_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    ip: str | None = None
    ua: str | None = None


class AuditLogPayload(BaseModel):
    id: int
    action: str
    user_id: str | None = None
    workspace_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime | None = None
