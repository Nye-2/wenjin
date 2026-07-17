"""Stable contracts for the durable Mission Runtime driver."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.contracts.model_usage import ModelUsageReceipt
from src.contracts.reasoning import ReasoningEffort
from src.contracts.review_policy import ReviewMode
from src.dataservice_client.contracts.mission import (
    MissionItemPayload,
    MissionReviewItemDraftPayload,
    MissionRunPayload,
)

MISSION_SLICE_WALL_TIME_SECONDS = 180.0
MISSION_SLICE_SHUTDOWN_MARGIN_SECONDS = 20.0
MISSION_SLICE_NEXT_STEP_RESERVE_SECONDS = 90.0
MISSION_MODEL_REQUEST_TIMEOUT_SECONDS = 165.0
MISSION_MODEL_MAX_OUTPUT_TOKENS = 8_192
MISSION_TASK_SOFT_TIME_LIMIT_SECONDS = 240
MISSION_TASK_HARD_TIME_LIMIT_SECONDS = 270
MISSION_BROKER_VISIBILITY_TIMEOUT_SECONDS = 3600
MISSION_WORKER_PREFETCH_MULTIPLIER = 1


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MissionContinuationDirective(_StrictModel):
    reason: Literal["needs_more_evidence", "regenerate"]
    review_item_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    reset_stage_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    rationale: str | None = Field(default=None, max_length=4000)


class MissionDecisionKind(StrEnum):
    CONTINUE = "continue"
    TOOL = "tool"
    SUBAGENT = "subagent"
    QUALITY = "quality"
    REVIEW = "review"
    PAUSE = "pause"
    COMPLETE = "complete"
    FAIL = "fail"


class MissionPortOutcomeStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING = "waiting"


class StageQualityVerdict(StrEnum):
    PASS = "pass"
    REVISE = "revise"
    ASK_USER = "ask_user"
    STOP = "stop"


class MissionSliceOutcome(StrEnum):
    COMPLETED = "completed"
    YIELDED = "yielded"
    WAITING = "waiting"
    TERMINAL = "terminal"


class MissionEventType(StrEnum):
    CREATED = "mission.created"
    UPDATED = "mission.updated"
    WAITING = "mission.waiting"
    COMPLETED = "mission.completed"
    FAILED = "mission.failed"
    CANCELLED = "mission.cancelled"


class MissionSliceLimits(_StrictModel):
    wall_time_seconds: float = Field(default=MISSION_SLICE_WALL_TIME_SECONDS, gt=0)
    shutdown_margin_seconds: float = Field(
        default=MISSION_SLICE_SHUTDOWN_MARGIN_SECONDS,
        gt=0,
    )
    max_model_turns: int = Field(default=4, ge=1, le=100)
    max_tool_steps: int = Field(default=8, ge=1, le=200)
    lease_ttl_seconds: int = Field(default=240, ge=5, le=3600)
    heartbeat_interval_seconds: float = Field(default=30.0, gt=0)
    max_consecutive_failures: int = Field(default=3, ge=1, le=20)
    max_transient_failures: int = Field(default=6, ge=1, le=20)
    max_operation_failures_per_stage: int = Field(default=8, ge=1, le=50)
    max_protocol_retries_per_step: int = Field(default=1, ge=0, le=3)
    next_step_reserve_seconds: float = Field(
        default=MISSION_SLICE_NEXT_STEP_RESERVE_SECONDS,
        gt=0,
    )

    @model_validator(mode="after")
    def validate_lease_margin(self) -> MissionSliceLimits:
        if self.wall_time_seconds + self.shutdown_margin_seconds >= self.lease_ttl_seconds:
            raise ValueError("lease_ttl_seconds must outlive the slice and shutdown margin")
        return self


class MissionStartRequest(_StrictModel):
    workspace_id: str = Field(min_length=1, max_length=36)
    thread_id: str | None = Field(default=None, max_length=36)
    user_id: str = Field(min_length=1, max_length=36)
    workspace_type: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=60)
    objective: str = Field(min_length=1, max_length=20_000)
    mission_idempotency_key: str = Field(min_length=1, max_length=160)
    mission_policy_id: str = Field(min_length=1, max_length=120)
    parent_mission_id: str | None = Field(default=None, max_length=36)
    continuation: MissionContinuationDirective | None = None
    review_mode: ReviewMode = ReviewMode.BALANCED_DEFAULT
    model_id: str = Field(min_length=1, max_length=120)
    reasoning_effort: ReasoningEffort
    snapshot_json: dict[str, Any] = Field(default_factory=dict)
    runtime_context_json: dict[str, Any] = Field(default_factory=dict)


class MissionStartReceipt(_StrictModel):
    mission_id: str
    status: str
    title: str
    created: bool
    wakeup_published: bool


class MissionPauseRequest(_StrictModel):
    request_id: str = Field(min_length=1, max_length=160)
    reason: Literal[
        "clarification",
        "approval",
        "user_input",
        "permission",
        "external_data",
        "budget",
        "review",
    ]
    summary: str = Field(min_length=1, max_length=4000)
    pending_request: dict[str, Any] = Field(default_factory=dict)


class MissionAgentDecision(_StrictModel):
    """One semantic decision with transport accounting attached after parsing."""

    decision_id: str = Field(min_length=1, max_length=160)
    kind: MissionDecisionKind
    summary: str = Field(min_length=1, max_length=4000)
    operation_id: str | None = Field(default=None, max_length=160)
    stage_id: str | None = Field(default=None, max_length=120)
    risk_level: Literal["low", "medium", "high"] | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    snapshot_patch: dict[str, Any] = Field(default_factory=dict)
    pause_request: MissionPauseRequest | None = None
    usage_receipt: ModelUsageReceipt | None = None

    @model_validator(mode="after")
    def validate_kind_fields(self) -> MissionAgentDecision:
        operation_kinds = {
            MissionDecisionKind.TOOL,
            MissionDecisionKind.SUBAGENT,
            MissionDecisionKind.QUALITY,
            MissionDecisionKind.REVIEW,
        }
        if self.kind in operation_kinds and not self.operation_id:
            raise ValueError(f"{self.kind.value} decision requires operation_id")
        if self.kind == MissionDecisionKind.PAUSE and self.pause_request is None:
            raise ValueError("pause decision requires pause_request")
        return self


class MissionAgentResponseError(RuntimeError):
    """Post-response processing failed after transport accounting was available."""

    def __init__(
        self,
        message: str,
        *,
        usage_receipt: ModelUsageReceipt | None = None,
    ) -> None:
        super().__init__(message)
        self.usage_receipt = usage_receipt


class MissionAgentProtocolError(MissionAgentResponseError):
    """A model response violated the structured Mission agent contract."""


class MissionAgentUsageError(RuntimeError):
    """A provider response could not produce a non-zero usage receipt."""


class MissionLoopContext(_StrictModel):
    mission: MissionRunPayload
    pending_commands: list[MissionItemPayload] = Field(default_factory=list)
    recent_items: list[MissionItemPayload] = Field(default_factory=list)
    reference_items: list[MissionItemPayload] = Field(
        default_factory=list,
        max_length=300,
    )
    model_turns_used: int = Field(ge=0)
    tool_steps_used: int = Field(ge=0)
    deadline_monotonic: float
    protocol_feedback: str | None = Field(default=None, max_length=1000)


class ToolExecutionRequest(_StrictModel):
    mission: MissionRunPayload
    operation_id: str
    tool_name: str = Field(min_length=1, max_length=160)
    arguments: dict[str, Any] = Field(default_factory=dict)
    stage_id: str | None = None
    recent_items: list[MissionItemPayload] = Field(default_factory=list, max_length=24)
    deadline_monotonic: float


class SubagentFrozenContext(_StrictModel):
    context_checkpoint_ref: str | None = Field(default=None, max_length=2048)
    context_checkpoint: dict[str, Any] = Field(default_factory=dict)
    prior_output_briefs: tuple[str, ...] = Field(default=(), max_length=8)


class SubagentExecutionRequest(_StrictModel):
    mission: MissionRunPayload
    operation_id: str
    task_summary: str = Field(min_length=1, max_length=4000)
    input_scope: dict[str, Any] = Field(default_factory=dict)
    stage_id: str | None = None
    frozen_context: SubagentFrozenContext
    deadline_monotonic: float


class StageQualityRequest(_StrictModel):
    mission: MissionRunPayload
    operation_id: str
    stage_id: str = Field(min_length=1, max_length=120)
    candidate_refs: list[str] = Field(default_factory=list, max_length=100)
    assessment_json: dict[str, Any] = Field(default_factory=dict)
    recent_items: list[MissionItemPayload] = Field(default_factory=list, max_length=100)
    reference_items: list[MissionItemPayload] = Field(default_factory=list, max_length=1000)
    deadline_monotonic: float


class ReviewCandidateRequest(_StrictModel):
    mission: MissionRunPayload
    operation_id: str
    stage_id: str | None = None
    candidate_json: dict[str, Any] = Field(default_factory=dict)
    accepted_candidate_refs: list[str] = Field(min_length=1, max_length=100)
    reference_items: list[MissionItemPayload] = Field(default_factory=list, max_length=1000)
    deadline_monotonic: float


class MissionPortOutcome(_StrictModel):
    status: MissionPortOutcomeStatus
    summary: str = Field(min_length=1, max_length=4000)
    payload_json: dict[str, Any] = Field(default_factory=dict)
    payload_ref: str | None = Field(default=None, max_length=2048)
    risk_level: Literal["low", "medium", "high"] | None = None
    snapshot_patch: dict[str, Any] = Field(default_factory=dict)
    pause_request: MissionPauseRequest | None = None

    @model_validator(mode="after")
    def validate_waiting_outcome(self) -> MissionPortOutcome:
        if self.status == MissionPortOutcomeStatus.WAITING and self.pause_request is None:
            raise ValueError("waiting port outcome requires pause_request")
        return self


class StageQualityOutcome(_StrictModel):
    verdict: StageQualityVerdict
    summary: str = Field(min_length=1, max_length=4000)
    payload_json: dict[str, Any] = Field(default_factory=dict)
    pause_request: MissionPauseRequest | None = None

    @model_validator(mode="after")
    def validate_pause(self) -> StageQualityOutcome:
        if self.verdict == StageQualityVerdict.ASK_USER and self.pause_request is None:
            raise ValueError("ask_user quality verdict requires pause_request")
        return self


class ReviewCandidateBatch(_StrictModel):
    items: list[MissionReviewItemDraftPayload] = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=4000)


class MissionEventEnvelope(_StrictModel):
    schema_version: Literal["1"] = "1"
    event_id: str
    event_type: MissionEventType
    mission_id: str
    workspace_id: str
    status: str
    state_version: int = Field(ge=0)
    last_item_seq: int = Field(ge=0)
    occurred_at: datetime


class MissionSliceTelemetry(_StrictModel):
    mission_id: str
    outcome: MissionSliceOutcome
    status: str
    reason: str
    state_version: int = Field(ge=0)
    last_item_seq: int = Field(ge=0)
    lease_epoch: int = Field(ge=0)
    model_turns: int = Field(ge=0)
    tool_steps: int = Field(ge=0)
    continuation_published: bool = False
    command_hint: str | None = Field(default=None, max_length=160)


__all__ = [name for name in globals() if name.startswith("Mission") or name.startswith("Stage") or name.endswith("Request") or name.endswith("Outcome") or name.startswith("MISSION_")]
