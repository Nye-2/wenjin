"""Pydantic models for compute API responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ComputeSessionResponse(BaseModel):
    """Compute session shell state."""

    id: str
    execution_session_id: str
    workspace_id: str
    user_id: str
    sandbox_session_id: str | None = None
    active_view: str = "overview"
    ui_state: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class ComputeSessionListResponse(BaseModel):
    """List of compute sessions."""

    items: list[ComputeSessionResponse]
    count: int


class ComputeProjectionResponse(BaseModel):
    """Aggregated Compute Stage projection."""

    compute_session: ComputeSessionResponse
    execution: dict[str, Any]
    primary_task: dict[str, Any] | None = None
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    runtime_blocks: list[dict[str, Any]] = Field(default_factory=list)
    subagents: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    runtime_profile: dict[str, Any] = Field(default_factory=dict)
    sandbox: dict[str, Any] = Field(default_factory=dict)
    prism: dict[str, Any] = Field(default_factory=dict)
    files: list[dict[str, Any]] = Field(default_factory=list)
    logs: list[dict[str, Any]] = Field(default_factory=list)
    review_gate: dict[str, Any] = Field(default_factory=dict)
