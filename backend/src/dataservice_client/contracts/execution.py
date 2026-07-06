"""Execution contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

EXECUTION_RESULT_PATCH_KEYS = frozenset(
    {"change_set_review_state", "change_unit_materialization"}
)
EXECUTION_COMMIT_FINALIZE_DELETABLE_RESULT_KEYS = frozenset(
    {"change_set", "change_set_review_state", "unit_states", "change_unit_materialization"}
)


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
    expected_status: str | None = None
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


class ExecutionResultPatchPayload(BaseModel):
    result_patch: dict[str, Any] = Field(default_factory=dict)

    @field_validator("result_patch")
    @classmethod
    def validate_result_patch_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        unsupported = sorted(set(value) - EXECUTION_RESULT_PATCH_KEYS)
        if unsupported:
            raise ValueError(
                "Unsupported execution result patch key(s): " + ", ".join(unsupported)
            )
        return dict(value)


class ExecutionLeaseClaimPayload(BaseModel):
    worker_id: str = Field(min_length=1, max_length=36)
    ttl_seconds: int = Field(default=120, ge=1, le=3600)
    claimed_at: datetime | None = None


class ExecutionLeaseHeartbeatPayload(BaseModel):
    worker_id: str = Field(min_length=1, max_length=36)
    ttl_seconds: int = Field(default=120, ge=1, le=3600)
    heartbeat_at: datetime | None = None


class ExecutionCommitClaimPayload(BaseModel):
    commit_token: str
    claimed_at: datetime | None = None


class ExecutionCommitFinalizePayload(BaseModel):
    commit_token: str
    result_json: dict[str, Any]
    delete_result_keys: list[str] = Field(default_factory=list)

    @field_validator("delete_result_keys")
    @classmethod
    def validate_delete_result_keys(cls, value: list[str]) -> list[str]:
        unsupported = sorted(set(value) - EXECUTION_COMMIT_FINALIZE_DELETABLE_RESULT_KEYS)
        if unsupported:
            raise ValueError(
                "Unsupported execution result delete key(s): " + ", ".join(unsupported)
            )
        return list(dict.fromkeys(value))


class ExecutionCommitFailPayload(BaseModel):
    commit_token: str
    error_text: str
    failed_at: datetime | None = None
    accepted_ids: list[str] | None = None
    rejected_ids: list[str] | None = None
    partial_counts: dict[str, Any] | None = None
    partial_room_targets: dict[str, Any] | None = None


class ExecutionCommitResetPayload(BaseModel):
    reason: str
    current_commit_token: str | None = None
    reset_at: datetime | None = None


class ComputeSessionEnsurePayload(BaseModel):
    execution_id: str
    workspace_id: str
    user_id: str
    sandbox_session_id: str | None = None


class ComputeSessionUpdatePayload(BaseModel):
    sandbox_session_id: str | None = None
    active_view: str | None = None
    ui_state: dict[str, Any] | None = None
    ui_state_delta: dict[str, Any] | None = None


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

    @property
    def feature_id(self) -> str | None:
        return self.capability_id

    @property
    def params(self) -> dict[str, Any]:
        return self.task_brief_json

    @property
    def result(self) -> dict[str, Any] | None:
        return self.result_json

    @property
    def error(self) -> str | None:
        return self.error_text

    @property
    def graph_structure(self) -> dict[str, Any] | None:
        return self.graph_json

    @property
    def node_states(self) -> dict[str, Any]:
        return self.node_states_json

    @property
    def runtime_state(self) -> dict[str, Any] | None:
        return self.runtime_state_json


class ComputeSessionPayload(BaseModel):
    id: str
    execution_id: str
    workspace_id: str
    user_id: str
    sandbox_session_id: str | None = None
    active_view: str = "overview"
    ui_state: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ExecutionEventCreatePayload(BaseModel):
    event_type: str
    workspace_id: str | None = None
    node_id: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class GenerationRecordCreatePayload(BaseModel):
    workspace_id: str
    skill_name: str
    thread_id: str | None = None
    model_name: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    duration_ms: int | None = None
    token_usage: dict[str, Any] | None = None
    status: str = "success"
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionNodeUpsertPayload(BaseModel):
    node_id: str
    node_type: str
    label: str | None = None
    parent_node_id: str | None = None
    status: str
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    thinking: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    token_usage: dict[str, Any] | None = None
    node_metadata: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ExecutionNodePatchPayload(BaseModel):
    status: str | None = None
    output_data: dict[str, Any] | None = None
    thinking: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    token_usage: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


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


class GenerationRecordPayload(BaseModel):
    id: str
    workspace_id: str
    thread_id: str | None = None
    skill_name: str
    model_name: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    duration_ms: int | None = None
    token_usage: dict[str, Any] | None = None
    status: str
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def total_tokens(self) -> int:
        if self.token_usage:
            return int(self.token_usage.get("total", 0))
        return 0

    @property
    def input_tokens(self) -> int:
        if self.token_usage:
            return int(self.token_usage.get("input", 0))
        return 0

    @property
    def output_tokens(self) -> int:
        if self.token_usage:
            return int(self.token_usage.get("output", 0))
        return 0


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
