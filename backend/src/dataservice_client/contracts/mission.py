"""Typed wire contracts for the canonical Mission DataService domain."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_MISSION_SNAPSHOT_BYTES = 64 * 1024
MAX_RUNTIME_CONTEXT_BYTES = 128 * 1024
MAX_MISSION_ITEM_PAYLOAD_BYTES = 64 * 1024
MAX_REVIEW_PREVIEW_BYTES = 128 * 1024

_SNAPSHOT_SCALAR_KEYS = frozenset(
    {
        "mission_id",
        "parent_mission_id",
        "workspace_id",
        "thread_id",
        "user_id",
        "workspace_type",
        "mission_policy_id",
        "title",
        "objective",
        "status",
        "review_mode",
        "active_stage_id",
        "model_id",
        "reasoning_effort",
        "context_checkpoint_ref",
        "mission_idempotency_key",
        "last_command_seq",
        "last_applied_command_seq",
        "next_wakeup_at",
        "lease_owner",
        "lease_epoch",
        "lease_expires_at",
        "state_version",
        "last_item_seq",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
    }
)
_SCALAR_COUNTER_KEYS = frozenset(
    {
        "pending_review_count",
        "evidence_count",
        "artifact_count",
        "active_subagent_count",
    }
)
_SUMMARY_KEYS = frozenset(
    {
        "evidence_ledger_summary",
        "subagent_summary",
        "review_summary",
        "commit_summary",
    }
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MissionStatus(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MissionReviewMode(StrEnum):
    REVIEW_ALL = "review_all"
    BALANCED_DEFAULT = "balanced_default"
    AUTO_DRAFT = "auto_draft"


class MissionReasoningEffort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class MissionItemPhase(StrEnum):
    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MissionRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MissionReviewStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    COMMITTED = "committed"
    SUPERSEDED = "superseded"


class MissionReviewDecisionStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    SUPERSEDED = "superseded"


class MissionCommitStatus(StrEnum):
    PENDING = "pending"
    APPLYING = "applying"
    COMMITTED = "committed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MissionOperationKind(StrEnum):
    TOOL = "tool"
    SANDBOX = "sandbox"


class MissionOperationStatus(StrEnum):
    CLAIMED = "claimed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


def _json_size(value: Any) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _bounded_json(value: dict[str, Any], *, maximum: int, label: str) -> dict[str, Any]:
    normalized = dict(value)
    if _json_size(normalized) > maximum:
        raise ValueError(f"{label} exceeds {maximum} bytes; externalize large content")
    return normalized


def _validate_snapshot(value: dict[str, Any]) -> dict[str, Any]:
    snapshot = _bounded_json(
        value,
        maximum=MAX_MISSION_SNAPSHOT_BYTES,
        label="snapshot_json",
    )
    duplicate_scalars = sorted(set(snapshot) & (_SNAPSHOT_SCALAR_KEYS | _SCALAR_COUNTER_KEYS))
    if duplicate_scalars:
        raise ValueError("snapshot_json duplicates canonical MissionRun scalar field(s): " + ", ".join(duplicate_scalars))
    for summary_key in _SUMMARY_KEYS:
        summary = snapshot.get(summary_key)
        if isinstance(summary, dict):
            duplicate_counters = sorted(set(summary) & _SCALAR_COUNTER_KEYS)
            if duplicate_counters:
                raise ValueError(f"snapshot_json.{summary_key} duplicates scalar counter(s): " + ", ".join(duplicate_counters))
    return snapshot


def validate_mission_snapshot(value: dict[str, Any]) -> dict[str, Any]:
    """Validate one complete bounded snapshot at non-Pydantic mutation boundaries."""
    return _validate_snapshot(value)


class MissionCreatePayload(_StrictModel):
    parent_mission_id: str | None = Field(default=None, max_length=36)
    workspace_id: str = Field(min_length=1, max_length=36)
    thread_id: str | None = Field(default=None, max_length=36)
    user_id: str = Field(min_length=1, max_length=36)
    workspace_type: str = Field(min_length=1, max_length=50)
    mission_policy_id: str | None = Field(default=None, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1, max_length=20_000)
    review_mode: MissionReviewMode = MissionReviewMode.BALANCED_DEFAULT
    model_id: str = Field(min_length=1, max_length=120)
    reasoning_effort: MissionReasoningEffort
    snapshot_json: dict[str, Any] = Field(default_factory=dict)
    runtime_context_json: dict[str, Any] = Field(default_factory=dict)
    mission_idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)

    @field_validator("snapshot_json")
    @classmethod
    def validate_snapshot(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_snapshot(value)

    @field_validator("runtime_context_json")
    @classmethod
    def validate_runtime_context(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _bounded_json(
            value,
            maximum=MAX_RUNTIME_CONTEXT_BYTES,
            label="runtime_context_json",
        )


class MissionRunPatchPayload(_StrictModel):
    status: MissionStatus | None = None
    active_stage_id: str | None = Field(default=None, max_length=120)
    context_checkpoint_ref: str | None = Field(default=None, max_length=2048)
    next_wakeup_at: datetime | None = None
    evidence_count_delta: int = Field(default=0, ge=0, le=10_000)
    artifact_count_delta: int = Field(default=0, ge=0, le=10_000)
    active_subagent_count_delta: int = Field(default=0, ge=-10_000, le=10_000)


class MissionItemDraftPayload(_StrictModel):
    item_type: str = Field(min_length=1, max_length=80)
    operation_id: str | None = Field(default=None, max_length=160)
    phase: MissionItemPhase
    stage_id: str | None = Field(default=None, max_length=120)
    producer: str | None = Field(default=None, max_length=160)
    summary: str | None = Field(default=None, max_length=4000)
    risk_level: MissionRiskLevel | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    payload_ref: str | None = Field(default=None, max_length=2048)

    @field_validator("payload_json")
    @classmethod
    def validate_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _bounded_json(
            value,
            maximum=MAX_MISSION_ITEM_PAYLOAD_BYTES,
            label="MissionItem.payload_json",
        )


class MissionAppendPayload(_StrictModel):
    expected_state_version: int = Field(ge=0)
    lease_owner: str = Field(min_length=1, max_length=160)
    lease_epoch: int = Field(ge=1)
    items: list[MissionItemDraftPayload] = Field(default_factory=list, max_length=100)
    snapshot_json: dict[str, Any] | None = None
    patch: MissionRunPatchPayload = Field(default_factory=MissionRunPatchPayload)

    @field_validator("snapshot_json")
    @classmethod
    def validate_snapshot(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_snapshot(value) if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> MissionAppendPayload:
        if not self.items and self.snapshot_json is None and not self.patch.model_fields_set:
            raise ValueError("append requires at least one item, snapshot, or scalar patch")
        return self


class MissionCheckpointPayload(MissionAppendPayload):
    snapshot_json: dict[str, Any]

    @field_validator("snapshot_json")
    @classmethod
    def validate_checkpoint_snapshot(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_snapshot(value)


class MissionLeaseClaimPayload(_StrictModel):
    worker_id: str = Field(min_length=1, max_length=160)
    expected_state_version: int = Field(ge=0)
    ttl_seconds: int = Field(default=120, ge=5, le=3600)


class MissionLeaseHeartbeatPayload(_StrictModel):
    worker_id: str = Field(min_length=1, max_length=160)
    lease_epoch: int = Field(ge=1)
    expected_state_version: int = Field(ge=0)
    ttl_seconds: int = Field(default=120, ge=5, le=3600)


class MissionLeaseReleasePayload(_StrictModel):
    worker_id: str = Field(min_length=1, max_length=160)
    lease_epoch: int = Field(ge=1)
    expected_state_version: int = Field(ge=0)
    next_wakeup_at: datetime | None = None


class MissionRunnableBatchClaimPayload(_StrictModel):
    worker_id: str = Field(min_length=1, max_length=160)
    ttl_seconds: int = Field(default=120, ge=5, le=3600)
    limit: int = Field(default=20, ge=1, le=100)


class MissionDispatchReleasePayload(_StrictModel):
    worker_id: str = Field(min_length=1, max_length=160)
    dispatch_epoch: int = Field(ge=1)


class MissionUserCommandPayload(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    command_type: str = Field(min_length=1, max_length=80)
    summary: str | None = Field(default=None, max_length=4000)
    producer: str = Field(default="workspace_agent", min_length=1, max_length=160)
    payload_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload_json")
    @classmethod
    def validate_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _bounded_json(
            value,
            maximum=MAX_MISSION_ITEM_PAYLOAD_BYTES,
            label="command.payload_json",
        )


class MissionApplyCommandsPayload(MissionAppendPayload):
    through_command_seq: int = Field(ge=1)


class MissionPausePayload(_StrictModel):
    request_id: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=80)
    pending_request: dict[str, Any] = Field(default_factory=dict)
    producer: str = Field(default="workspace_agent", min_length=1, max_length=160)


class MissionResumePayload(_StrictModel):
    request_id: str = Field(min_length=1, max_length=160)
    input_json: dict[str, Any] = Field(default_factory=dict)
    producer: str = Field(default="workspace_agent", min_length=1, max_length=160)


class MissionCancelPayload(_StrictModel):
    request_id: str = Field(min_length=1, max_length=160)
    reason: str | None = Field(default=None, max_length=4000)
    producer: str = Field(default="workspace_agent", min_length=1, max_length=160)


class MissionReviewItemDraftPayload(_StrictModel):
    review_item_id: str = Field(default_factory=lambda: str(uuid4()), max_length=36)
    source_item_seq: int | None = Field(default=None, ge=1)
    target_kind: str = Field(min_length=1, max_length=80)
    target_room: str | None = Field(default=None, max_length=80)
    target_ref: str | None = Field(default=None, max_length=2048)
    base_revision_ref: str | None = Field(default=None, max_length=2048)
    base_hash: str | None = Field(default=None, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=4000)
    risk_level: MissionRiskLevel
    review_required_reason: str | None = Field(default=None, max_length=4000)
    preview_json: dict[str, Any] = Field(default_factory=dict)
    preview_ref: str | None = Field(default=None, max_length=2048)
    preview_expires_at: datetime | None = None

    @field_validator("preview_json")
    @classmethod
    def validate_preview(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _bounded_json(
            value,
            maximum=MAX_REVIEW_PREVIEW_BYTES,
            label="preview_json",
        )


class MissionReviewItemsCreatePayload(_StrictModel):
    expected_state_version: int = Field(ge=0)
    lease_owner: str = Field(min_length=1, max_length=160)
    lease_epoch: int = Field(ge=1)
    items: list[MissionReviewItemDraftPayload] = Field(min_length=1, max_length=100)


class MissionReviewDecisionPayload(_StrictModel):
    review_item_id: str = Field(min_length=1, max_length=36)
    status: MissionReviewDecisionStatus
    decision_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("decision_json")
    @classmethod
    def validate_decision(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _bounded_json(
            value,
            maximum=MAX_MISSION_ITEM_PAYLOAD_BYTES,
            label="decision_json",
        )


class MissionReviewDecisionsPayload(_StrictModel):
    decision_id: str = Field(min_length=1, max_length=160)
    expected_state_version: int = Field(ge=0)
    actor_user_id: str = Field(min_length=1, max_length=36)
    decisions: list[MissionReviewDecisionPayload] = Field(min_length=1, max_length=100)

    @field_validator("decisions")
    @classmethod
    def unique_review_items(cls, value: list[MissionReviewDecisionPayload]) -> list[MissionReviewDecisionPayload]:
        identifiers = [item.review_item_id for item in value]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("review_item_id values must be unique within one decision")
        return value


class MissionCommitCreatePayload(_StrictModel):
    expected_state_version: int = Field(ge=0)
    review_item_id: str = Field(min_length=1, max_length=36)
    commit_key: str = Field(min_length=1, max_length=160)
    actor_user_id: str = Field(min_length=1, max_length=36)


class MissionCommitStartPayload(_StrictModel):
    attempt_token: str = Field(min_length=16, max_length=160)
    lease_seconds: int = Field(default=120, ge=5, le=3600)


class MissionCommitFinishPayload(_StrictModel):
    attempt_token: str = Field(min_length=16, max_length=160)
    status: MissionCommitStatus
    targets_json: dict[str, Any] = Field(default_factory=dict)
    error_json: dict[str, Any] | None = None

    @field_validator("targets_json")
    @classmethod
    def validate_targets(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _bounded_json(
            value,
            maximum=MAX_MISSION_ITEM_PAYLOAD_BYTES,
            label="targets_json",
        )

    @field_validator("error_json")
    @classmethod
    def validate_error(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return _bounded_json(
            value,
            maximum=MAX_MISSION_ITEM_PAYLOAD_BYTES,
            label="error_json",
        )

    @model_validator(mode="after")
    def validate_terminal_status(self) -> MissionCommitFinishPayload:
        if self.status not in {
            MissionCommitStatus.COMMITTED,
            MissionCommitStatus.FAILED,
            MissionCommitStatus.CANCELLED,
        }:
            raise ValueError("commit finish status must be committed, failed, or cancelled")
        if self.status == MissionCommitStatus.FAILED and self.error_json is None:
            raise ValueError("failed commit requires error_json")
        return self


class MissionPreviewCleanupPayload(_StrictModel):
    now: datetime
    limit: int = Field(default=200, ge=1, le=1000)


class MissionPreviewCleanupResultPayload(_StrictModel):
    review_item_ids: list[str]
    preview_refs: list[str]


class MissionRunPayload(_StrictModel):
    mission_id: str
    parent_mission_id: str | None = None
    workspace_id: str
    thread_id: str | None = None
    user_id: str
    workspace_type: str
    mission_policy_id: str | None = None
    title: str
    objective: str
    status: MissionStatus
    review_mode: MissionReviewMode
    active_stage_id: str | None = None
    model_id: str
    reasoning_effort: MissionReasoningEffort
    snapshot_json: dict[str, Any] = Field(default_factory=dict)
    runtime_context_json: dict[str, Any] = Field(default_factory=dict)
    context_checkpoint_ref: str | None = None
    pending_review_count: int
    evidence_count: int
    artifact_count: int
    active_subagent_count: int
    mission_idempotency_key: str | None = None
    last_command_seq: int
    last_applied_command_seq: int
    next_wakeup_at: datetime | None = None
    lease_owner: str | None = None
    lease_epoch: int
    lease_expires_at: datetime | None = None
    dispatch_owner: str | None = None
    dispatch_epoch: int = 0
    dispatch_expires_at: datetime | None = None
    state_version: int
    last_item_seq: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class MissionRunPagePayload(_StrictModel):
    items: list[MissionRunPayload]
    next_cursor: str | None = None


class MissionItemPayload(_StrictModel):
    id: str
    mission_id: str
    seq: int
    item_type: str
    operation_id: str | None = None
    phase: MissionItemPhase
    stage_id: str | None = None
    producer: str | None = None
    summary: str | None = None
    risk_level: MissionRiskLevel | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    payload_ref: str | None = None
    created_at: datetime


class MissionOperationClaimPayload(_StrictModel):
    operation_key: str = Field(min_length=1, max_length=200)
    kind: MissionOperationKind
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    claimant: str = Field(min_length=1, max_length=200)
    lease_epoch: int = Field(ge=1)
    ttl_seconds: int = Field(default=180, ge=5, le=3600)


class MissionOperationFinishPayload(_StrictModel):
    operation_key: str = Field(min_length=1, max_length=200)
    kind: MissionOperationKind
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    claimant: str = Field(min_length=1, max_length=200)
    lease_epoch: int = Field(ge=1)
    status: MissionOperationStatus
    receipt_json: dict[str, Any] = Field(default_factory=dict)
    payload_ref: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def terminal_only(self) -> MissionOperationFinishPayload:
        if self.status is MissionOperationStatus.CLAIMED:
            raise ValueError("operation finish status must be terminal")
        return self


class MissionOperationReceiptPayload(_StrictModel):
    receipt_id: str
    mission_id: str
    operation_key: str
    kind: MissionOperationKind
    request_hash: str
    status: MissionOperationStatus
    claimant: str
    lease_epoch: int
    lease_expires_at: datetime | None = None
    receipt_json: dict[str, Any] = Field(default_factory=dict)
    payload_ref: str | None = None
    attempt: int
    claimed_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class MissionOperationClaimResultPayload(_StrictModel):
    receipt: MissionOperationReceiptPayload
    acquired: bool


class MissionOperationFinishResultPayload(_StrictModel):
    receipt: MissionOperationReceiptPayload
    finalized: bool


class MissionReviewItemPayload(_StrictModel):
    review_item_id: str
    mission_id: str
    source_item_seq: int | None = None
    target_kind: str
    target_room: str | None = None
    target_ref: str | None = None
    base_revision_ref: str | None = None
    base_hash: str | None = None
    title: str
    summary: str | None = None
    risk_level: MissionRiskLevel
    status: MissionReviewStatus
    review_required_reason: str | None = None
    preview_json: dict[str, Any] = Field(default_factory=dict)
    preview_ref: str | None = None
    preview_hash: str | None = None
    preview_expires_at: datetime | None = None
    requires_explicit_review: bool
    batch_acceptable: bool
    suggested_selected: bool
    decision_json: dict[str, Any] | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class MissionCommitPayload(_StrictModel):
    commit_id: str
    mission_id: str
    review_item_id: str
    commit_key: str
    status: MissionCommitStatus
    actor_user_id: str
    targets_json: dict[str, Any] = Field(default_factory=dict)
    error_json: dict[str, Any] | None = None
    attempt_count: int
    attempt_token: str | None = None
    attempt_started_at: datetime | None = None
    attempt_expires_at: datetime | None = None
    created_at: datetime
    completed_at: datetime | None = None


class MissionReviewSummaryPayload(_StrictModel):
    pending: int = 0
    accepted: int = 0
    rejected: int = 0
    needs_more_evidence: int = 0
    committed: int = 0
    superseded: int = 0


class MissionCommitSummaryPayload(_StrictModel):
    pending: int = 0
    applying: int = 0
    committed: int = 0
    failed: int = 0
    cancelled: int = 0


class MissionStatsKpisPayload(_StrictModel):
    total: int = Field(ge=0)
    success: int = Field(ge=0)
    failed: int = Field(ge=0)
    success_rate: float = Field(ge=0.0, le=1.0)


class MissionStatsTimePointPayload(_StrictModel):
    date: str
    by_type: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)


class MissionWorkspaceTypeCountPayload(_StrictModel):
    type: str
    count: int = Field(ge=0)


class MissionStatsPayload(_StrictModel):
    kpis: MissionStatsKpisPayload
    time_series: list[MissionStatsTimePointPayload]
    by_workspace_type: list[MissionWorkspaceTypeCountPayload]


class MissionStageSummaryPayload(_StrictModel):
    stage_id: str
    title: str
    status: str
    summary: str | None = None


class MissionSubagentSummaryPayload(_StrictModel):
    subagent_id: str
    display_name: str
    role_label: str
    status: str
    summary: str | None = None


class MissionEvidenceSummaryPayload(_StrictModel):
    item_id: str
    seq: int
    title: str
    source_type: str
    source_label: str | None = None
    summary: str | None = None
    citation: str | None = None
    verified: bool = False


class MissionArtifactSummaryPayload(_StrictModel):
    item_id: str
    seq: int
    title: str
    kind: str
    summary: str | None = None
    preview_available: bool = False
    committed: bool = False


class MissionReviewPolicyPayload(_StrictModel):
    mode: MissionReviewMode
    protected_outputs_require_confirmation: bool = True
    draft_outputs_may_be_automatic: bool


class MissionAttentionInputPayload(_StrictModel):
    input_id: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=400)
    description: str | None = Field(default=None, max_length=2000)
    input_type: str = Field(pattern=r"^(text|file|confirmation|credits)$")
    required: bool = True


class MissionAttentionActionPayload(_StrictModel):
    action_id: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=160)
    action_type: str = Field(pattern=r"^(reply_in_chat|upload_file|open_review)$")
    primary: bool = False


class MissionAttentionRequestPayload(_StrictModel):
    request_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=400)
    summary: str = Field(min_length=1, max_length=2000)
    impact: str = Field(min_length=1, max_length=2000)
    required_inputs: list[MissionAttentionInputPayload] = Field(default_factory=list, max_length=32)
    actions: list[MissionAttentionActionPayload] = Field(default_factory=list, min_length=1, max_length=8)


class MissionProjectionPagePayload(_StrictModel):
    total: int = Field(ge=0)
    returned: int = Field(ge=0)
    next_cursor: int | None = None


class MissionViewPayload(_StrictModel):
    mission: MissionRunPayload
    attention_request: MissionAttentionRequestPayload | None
    review_summary: MissionReviewSummaryPayload
    commit_summary: MissionCommitSummaryPayload
    review_items: list[MissionReviewItemPayload] = Field(default_factory=list)
    commits: list[MissionCommitPayload] = Field(default_factory=list)
    required_stage_ids: list[str] = Field(default_factory=list)
    stage_summaries: list[MissionStageSummaryPayload] = Field(default_factory=list)
    team_summary: str | None = None
    subagents: list[MissionSubagentSummaryPayload] = Field(default_factory=list)
    evidence_items: list[MissionEvidenceSummaryPayload] = Field(default_factory=list)
    evidence_page: MissionProjectionPagePayload
    artifact_items: list[MissionArtifactSummaryPayload] = Field(default_factory=list)
    artifact_page: MissionProjectionPagePayload
    review_policy: MissionReviewPolicyPayload
    quality_highlights: list[str] = Field(default_factory=list)
    refresh_token: str


class MissionCreateResultPayload(_StrictModel):
    mission: MissionRunPayload
    created: bool


class MissionAppendResultPayload(_StrictModel):
    mission: MissionRunPayload
    items: list[MissionItemPayload]


class MissionReviewItemsResultPayload(_StrictModel):
    mission: MissionRunPayload
    items: list[MissionReviewItemPayload]


class MissionCommitCreateResultPayload(_StrictModel):
    mission: MissionRunPayload
    commit: MissionCommitPayload
    created: bool


class MissionCommitResultPayload(_StrictModel):
    mission: MissionRunPayload
    commit: MissionCommitPayload


__all__ = [name for name in globals() if name.startswith("Mission") or name.startswith("MAX_") or name == "validate_mission_snapshot"]
