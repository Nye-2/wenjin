"""Execution domain contracts."""

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


class ExecutionCreateCommand(BaseModel):
    """Create one product execution."""

    execution_type: str = Field(min_length=1, max_length=50)
    user_id: str = Field(min_length=1, max_length=36)
    workspace_id: str | None = Field(default=None, max_length=36)
    thread_id: str | None = Field(default=None, max_length=36)
    capability_id: str | None = Field(default=None, max_length=100)
    entry_skill_id: str | None = Field(default=None, max_length=100)
    workspace_type: str | None = Field(default=None, max_length=50)
    display_name: str | None = Field(default=None, max_length=200)
    task_brief_json: dict[str, Any] = Field(default_factory=dict)
    parent_execution_id: str | None = Field(default=None, max_length=36)


class ExecutionUpdateCommand(BaseModel):
    """Patch product execution state."""

    expected_status: str | None = Field(default=None, max_length=32)
    status: str | None = Field(default=None, max_length=32)
    thread_id: str | None = Field(default=None, max_length=36)
    entry_skill_id: str | None = Field(default=None, max_length=100)
    workspace_type: str | None = Field(default=None, max_length=50)
    display_name: str | None = Field(default=None, max_length=200)
    task_brief_json: dict[str, Any] | None = None
    result_json: dict[str, Any] | None = None
    error_text: str | None = None
    result_summary: str | None = None
    graph_json: dict[str, Any] | None = None
    node_states_json: dict[str, Any] | None = None
    runtime_state_json: dict[str, Any] | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    message: str | None = None
    artifact_ids: list[str] | None = None
    next_actions: list[dict[str, Any]] | None = None
    advisory_code: str | None = Field(default=None, max_length=100)
    last_error: str | None = None
    dispatch_mode: str | None = Field(default=None, max_length=20)
    worker_task_id: str | None = Field(default=None, max_length=36)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ExecutionResultPatchCommand(BaseModel):
    """Atomically merge keys into execution.result."""

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


class ExecutionLeaseClaimCommand(BaseModel):
    """Atomically reserve one in-flight execution for a worker."""

    worker_id: str = Field(min_length=1, max_length=36)
    ttl_seconds: int = Field(default=120, ge=1, le=3600)
    claimed_at: datetime | None = None


class ExecutionLeaseHeartbeatCommand(BaseModel):
    """Extend an owned in-flight execution lease."""

    worker_id: str = Field(min_length=1, max_length=36)
    ttl_seconds: int = Field(default=120, ge=1, le=3600)
    heartbeat_at: datetime | None = None


class ExecutionCommitClaimCommand(BaseModel):
    """Atomically reserve execution result commit materialization."""

    commit_token: str = Field(min_length=1, max_length=64)
    claimed_at: datetime | None = None


class ExecutionCommitFinalizeCommand(BaseModel):
    """Finalize a previously claimed execution result commit."""

    commit_token: str = Field(min_length=1, max_length=64)
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


class ExecutionCommitFailCommand(BaseModel):
    """Record a failed execution result commit attempt for manual recovery."""

    commit_token: str = Field(min_length=1, max_length=64)
    error_text: str
    failed_at: datetime | None = None
    accepted_ids: list[str] | None = None
    rejected_ids: list[str] | None = None
    partial_counts: dict[str, Any] | None = None
    partial_room_targets: dict[str, Any] | None = None


class ExecutionCommitResetCommand(BaseModel):
    """Clear a non-terminal commit claim after explicit operator recovery."""

    reason: str = Field(min_length=1)
    current_commit_token: str | None = Field(default=None, min_length=1, max_length=64)
    reset_at: datetime | None = None


class ExecutionEventCreateCommand(BaseModel):
    """Append one ordered execution event."""

    event_type: str = Field(min_length=1, max_length=120)
    workspace_id: str | None = Field(default=None, max_length=36)
    node_id: str | None = Field(default=None, max_length=100)
    payload_json: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class GenerationRecordCreateCommand(BaseModel):
    """Record one skill-generation usage event behind DataService."""

    workspace_id: str = Field(min_length=1, max_length=36)
    skill_name: str = Field(min_length=1, max_length=100)
    thread_id: str | None = Field(default=None, max_length=36)
    model_name: str | None = Field(default=None, max_length=100)
    input_summary: str | None = None
    output_summary: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    token_usage: dict[str, Any] | None = None
    status: str = Field(default="success", max_length=20)
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionNodeUpsertCommand(BaseModel):
    """Create or update one execution node lifecycle snapshot."""

    node_id: str = Field(min_length=1, max_length=100)
    node_type: str = Field(min_length=1, max_length=20)
    label: str | None = Field(default=None, max_length=200)
    parent_node_id: str | None = Field(default=None, max_length=36)
    status: str = Field(min_length=1, max_length=20)
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    thinking: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    token_usage: dict[str, Any] | None = None
    node_metadata: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ExecutionNodePatchCommand(BaseModel):
    """Patch one execution node lifecycle snapshot by storage id."""

    status: str | None = Field(default=None, max_length=20)
    output_data: dict[str, Any] | None = None
    thinking: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    token_usage: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ComputeSessionEnsureCommand(BaseModel):
    """Ensure a compute work-plane shell exists for an execution."""

    execution_id: str = Field(min_length=1, max_length=36)
    workspace_id: str = Field(min_length=1, max_length=36)
    user_id: str = Field(min_length=1, max_length=36)
    sandbox_session_id: str | None = Field(default=None, max_length=100)


class ComputeSessionUpdateCommand(BaseModel):
    """Update mutable compute shell state."""

    sandbox_session_id: str | None = Field(default=None, max_length=100)
    active_view: str | None = Field(default=None, max_length=50)
    ui_state: dict[str, Any] | None = None
    ui_state_delta: dict[str, Any] | None = None


class ExecutionRecordProjection(BaseModel):
    """Canonical execution projection with v2 field names."""

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


class ComputeSessionProjection(BaseModel):
    """Rebuildable compute work-plane shell projection."""

    id: str
    execution_id: str
    workspace_id: str
    user_id: str
    sandbox_session_id: str | None = None
    active_view: str = "overview"
    ui_state: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ExecutionNodeProjection(BaseModel):
    """Canonical execution node projection."""

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


class ExecutionEventProjection(BaseModel):
    """Canonical execution event projection."""

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


class GenerationRecordProjection(BaseModel):
    """Projection for generation usage rows owned by DataService."""

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


class ExecutionRunHistoryProjection(BaseModel):
    """Run-history projection derived from the execution aggregate."""

    id: str
    workspace_id: str | None = None
    execution_id: str
    capability_id: str | None = None
    title: str
    summary: str | None = None
    status: str
    duration_seconds: int = 0
    token_usage: dict[str, Any] | None = None
    artifact_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
