"""Execution contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ExecutionCreatePayload(BaseModel):
    execution_type: str
    user_id: str
    workspace_id: str | None = None
    thread_id: str | None = None
    capability_id: str | None = None
    entry_skill_id: str | None = None
    workspace_type: str | None = None
    display_name: str | None = None
    task_brief_json: dict[str, Any] = Field(default_factory=dict)
    parent_execution_id: str | None = None


class ExecutionUpdatePayload(BaseModel):
    status: str | None = None
    thread_id: str | None = None
    entry_skill_id: str | None = None
    workspace_type: str | None = None
    display_name: str | None = None
    task_brief_json: dict[str, Any] | None = None
    result_json: dict[str, Any] | None = None
    error_text: str | None = None
    result_summary: str | None = None
    graph_json: dict[str, Any] | None = None
    node_states_json: dict[str, Any] | None = None
    runtime_state_json: dict[str, Any] | None = None
    progress: int | None = None
    message: str | None = None
    artifact_ids: list[str] | None = None
    next_actions: list[dict[str, Any]] | None = None
    advisory_code: str | None = None
    last_error: str | None = None
    dispatch_mode: str | None = None
    worker_task_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ExecutionPayload(BaseModel):
    id: str
    user_id: str
    workspace_id: str | None = None
    thread_id: str | None = None
    execution_type: str
    capability_id: str | None = None
    entry_skill_id: str | None = None
    workspace_type: str | None = None
    display_name: str | None = None
    status: str
    task_brief_json: dict[str, Any] = Field(default_factory=dict)
    result_json: dict[str, Any] | None = None
    error_text: str | None = None
    result_summary: str | None = None
    graph_json: dict[str, Any] | None = None
    node_states_json: dict[str, Any] = Field(default_factory=dict)
    runtime_state_json: dict[str, Any] | None = None
    progress: int = 0
    message: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    next_actions: list[dict[str, Any]] = Field(default_factory=list)
    advisory_code: str | None = None
    last_error: str | None = None
    parent_execution_id: str | None = None
    child_execution_ids: list[str] = Field(default_factory=list)
    dispatch_mode: str | None = None
    worker_task_id: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None


class ExecutionEventCreatePayload(BaseModel):
    event_type: str
    workspace_id: str | None = None
    node_id: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class ExecutionEventPayload(BaseModel):
    id: str
    execution_id: str
    workspace_id: str | None = None
    node_id: str | None = None
    event_type: str
    sequence_index: int
    payload_json: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ExecutionNodePayload(BaseModel):
    id: str
    execution_id: str
    parent_node_id: str | None = None
    node_id: str
    node_type: str
    label: str | None = None
    status: str
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    thinking: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    token_usage: dict[str, Any] | None = None
    node_metadata: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
