"""Strict contracts for bounded, mission-owned subagent jobs."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.contracts.model_usage import ModelUsageReceipt
from src.contracts.reasoning import ReasoningEffort

SUBAGENT_MIN_RUNTIME_CONTEXT_BYTES = 24_000
SUBAGENT_MIN_RUNTIME_TOOL_STEPS = 8


def subagent_context_size_bytes(payload: dict[str, Any]) -> int:
    """Measure the exact bounded context payload used by SubagentJobSpec."""

    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    )


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SubagentStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class SubagentStopReason(StrEnum):
    NORMAL = "normal"
    TOKEN_CAPPED = "token_capped"
    TURN_CAPPED = "turn_capped"
    LOOP_CAPPED = "loop_capped"
    DEADLINE_REACHED = "deadline_reached"
    TOOL_UNAVAILABLE = "tool_unavailable"
    PERMISSION_DENIED = "permission_denied"
    MALFORMED_TOOL_ARGUMENTS = "malformed_tool_arguments"
    MALFORMED_MODEL_OUTPUT = "malformed_model_output"
    MODEL_ERROR = "model_error"
    CANCELLED = "cancelled"
    PARTIAL_RESULT_AVAILABLE = "partial_result_available"


class SubagentModelOutputError(ValueError):
    """The provider returned an invalid structured subagent action."""

    def __init__(
        self,
        message: str,
        *,
        usage_receipt: ModelUsageReceipt,
    ) -> None:
        super().__init__(message)
        self.usage_receipt = usage_receipt


class SubagentModelUsageError(RuntimeError):
    """A provider response could not produce a non-zero usage receipt."""


class SubagentBudget(_FrozenModel):
    max_turns: int = Field(default=6, ge=1, le=24)
    max_tool_steps: int = Field(default=SUBAGENT_MIN_RUNTIME_TOOL_STEPS, ge=0, le=32)
    max_context_bytes: int = Field(default=96_000, ge=4_096, le=512_000)
    max_result_bytes: int = Field(default=64_000, ge=1_024, le=512_000)


class SubagentContextRead(_FrozenModel):
    ref: str = Field(min_length=1, max_length=2_048)
    tool_name: str = Field(min_length=1, max_length=160)
    arguments: dict[str, Any]


class SubagentJobSpec(_FrozenModel):
    job_id: str = Field(min_length=1, max_length=160)
    operation_id: str = Field(min_length=1, max_length=160)
    mission_id: str = Field(min_length=1, max_length=160)
    workspace_id: str = Field(min_length=1, max_length=160)
    model_id: str = Field(min_length=1, max_length=160)
    reasoning_effort: ReasoningEffort
    lease_owner: str = Field(min_length=1, max_length=160)
    lease_epoch: int = Field(ge=1)
    stage_id: str | None = Field(default=None, max_length=120)
    display_name: str = Field(min_length=1, max_length=80)
    role_label: str = Field(min_length=1, max_length=80)
    task_summary: str = Field(min_length=1, max_length=4_000)
    objective: str = Field(min_length=1, max_length=20_000)
    input_scope: dict[str, Any] = Field(default_factory=dict)
    context_checkpoint_ref: str | None = Field(default=None, max_length=2_048)
    context_checkpoint: dict[str, Any] = Field(default_factory=dict)
    selected_refs: tuple[str, ...] = Field(default=(), max_length=100)
    context_reads: tuple[SubagentContextRead, ...] = Field(default=(), max_length=100)
    prior_output_briefs: tuple[str, ...] = Field(default=(), max_length=12)
    allowed_tools: tuple[str, ...] = Field(default=(), max_length=64)
    tool_input_schemas: dict[str, dict[str, Any]] = Field(default_factory=dict)
    worker_skill: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    exit_criteria: tuple[str, ...] = Field(default=(), max_length=32)
    budget: SubagentBudget = Field(default_factory=SubagentBudget)
    depth: Literal[1] = 1

    @field_validator("input_scope")
    @classmethod
    def reject_parent_history(cls, value: dict[str, Any]) -> dict[str, Any]:
        forbidden = {"messages", "chat_history", "full_transcript", "raw_tool_logs", "workspace_data"}
        found = sorted(forbidden.intersection(value))
        if found:
            raise ValueError("subagent input_scope contains forbidden parent context: " + ", ".join(found))
        return value

    @model_validator(mode="after")
    def enforce_context_budget(self) -> SubagentJobSpec:
        payload = self.model_dump(mode="json", exclude={"budget"})
        size = subagent_context_size_bytes(payload)
        if size > self.budget.max_context_bytes:
            raise ValueError("subagent context exceeds max_context_bytes")
        if len(self.allowed_tools) != len(set(self.allowed_tools)):
            raise ValueError("allowed_tools must be unique")
        if len(self.selected_refs) != len(set(self.selected_refs)):
            raise ValueError("selected_refs must be unique")
        if set(self.tool_input_schemas) != set(self.allowed_tools):
            raise ValueError("tool_input_schemas must exactly match allowed_tools")
        context_read_refs = [item.ref for item in self.context_reads]
        if len(context_read_refs) != len(set(context_read_refs)):
            raise ValueError("context_reads must have unique refs")
        if not set(context_read_refs).issubset(self.selected_refs):
            raise ValueError("context_reads must resolve selected_refs")
        if not {item.tool_name for item in self.context_reads}.issubset(self.allowed_tools):
            raise ValueError("context_reads must use allowed_tools")
        if len(self.context_reads) > self.budget.max_tool_steps:
            raise ValueError("context_reads exceed max_tool_steps")
        return self


class SubagentToolRequest(_FrozenModel):
    job_id: str
    operation_id: str
    mission_id: str
    workspace_id: str
    lease_owner: str
    lease_epoch: int = Field(ge=1)
    stage_id: str | None = None
    tool_name: str = Field(min_length=1, max_length=160)
    arguments: dict[str, Any]


class SubagentToolResult(_FrozenModel):
    status: Literal["completed", "failed"]
    summary: str = Field(min_length=1, max_length=2_000)
    payload_json: dict[str, Any] = Field(default_factory=dict)
    payload_ref: str | None = Field(default=None, max_length=2_048)
    evidence_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    recoverable: bool = False
    error_type: str | None = Field(default=None, max_length=80)


class SubagentAction(_FrozenModel):
    kind: Literal["tool", "complete", "stop"]
    summary: str = Field(min_length=1, max_length=4_000)
    tool_name: str | None = Field(default=None, max_length=160)
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_json: dict[str, Any] = Field(default_factory=dict)
    partial_result_json: dict[str, Any] = Field(default_factory=dict)
    stop_reason: SubagentStopReason | None = None

    @model_validator(mode="after")
    def validate_action(self) -> SubagentAction:
        if self.kind == "tool" and not self.tool_name:
            raise ValueError("tool action requires tool_name")
        if self.kind == "complete" and self.stop_reason not in {None, SubagentStopReason.NORMAL}:
            raise ValueError("complete action can only use normal stop_reason")
        if self.kind == "stop" and self.stop_reason is None:
            raise ValueError("stop action requires stop_reason")
        return self


class SubagentModelTurn(_FrozenModel):
    """One provider response: semantic action plus transport accounting."""

    action: SubagentAction
    usage_receipt: ModelUsageReceipt

    @model_validator(mode="after")
    def require_non_zero_usage(self) -> SubagentModelTurn:
        if self.usage_receipt.usage.total_tokens <= 0:
            raise ValueError("subagent provider response requires non-zero usage")
        return self


class SubagentStep(_FrozenModel):
    turn: int = Field(ge=1)
    kind: Literal["tool", "tool_result", "progress"]
    summary: str = Field(min_length=1, max_length=2_000)
    tool_name: str | None = None
    payload_ref: str | None = None


class SubagentJobResult(_FrozenModel):
    job_id: str
    operation_id: str
    display_name: str
    role_label: str
    status: SubagentStatus
    stop_reason: SubagentStopReason
    result_brief: str = Field(min_length=1, max_length=4_000)
    result_json: dict[str, Any] = Field(default_factory=dict)
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    turns_used: int = Field(ge=0)
    tool_steps_used: int = Field(ge=0)
    partial_result_available: bool = False


class SubagentBatchResult(_FrozenModel):
    operation_id: str
    results: tuple[SubagentJobResult, ...] = Field(min_length=1)


__all__ = [name for name in globals() if name.startswith("Subagent")]
