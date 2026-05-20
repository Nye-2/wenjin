"""Outbox event primitives."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OutboxEventDraft(BaseModel):
    """Validated outbox event input before ORM persistence."""

    aggregate_kind: str = Field(min_length=1, max_length=80)
    aggregate_id: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=120)
    payload_json: dict[str, Any]
    workspace_id: str | None = None
