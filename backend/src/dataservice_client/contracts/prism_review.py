"""Prism review contracts returned by DataService client methods."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PrismFileChangeUpsertPayload(BaseModel):
    workspace_id: str
    latex_project_id: str
    logical_key: str
    path: str
    reason: str
    pending_content: str
    pending_hash: str
    current_hash: str | None = None
    source_execution_id: str | None = None
    source_task_id: str | None = None


class PrismFileChangeClearPayload(BaseModel):
    workspace_id: str
    latex_project_id: str
    logical_key: str


class PrismFileChangeAppliedPayload(BaseModel):
    previous_content: str
    previous_hash: str
    applied_hash: str
    revert_signature: str


class PrismFileChangeRejectedPayload(BaseModel):
    reason: str | None = None


class PrismFileChangeRevertedPayload(BaseModel):
    payload_json: dict[str, Any] = Field(default_factory=dict)
