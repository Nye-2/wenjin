"""Canonical contracts for every Mission Runtime tool invocation."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ToolKind(StrEnum):
    READ = "read"
    COMPUTE = "compute"
    SANDBOX_MUTATION = "sandbox_mutation"
    WRITE_CANDIDATE = "write_candidate"


class SideEffectClass(StrEnum):
    NONE = "none"
    IDEMPOTENT = "idempotent"
    NON_IDEMPOTENT = "non_idempotent"


class ToolCallerKind(StrEnum):
    WORKSPACE_AGENT = "workspace_agent"
    SUBAGENT = "subagent"
    SYSTEM = "system"


class ToolOutcomeStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"


class ToolErrorType(StrEnum):
    RATE_LIMITED = "rate_limited"
    NO_RESULTS = "no_results"
    AUTH_REQUIRED = "auth_required"
    PERMISSION_DENIED = "permission_denied"
    TOOL_UNAVAILABLE = "tool_unavailable"
    INVALID_INPUT = "invalid_input"
    POLICY_FORBIDDEN = "policy_forbidden"
    TIMEOUT = "timeout"
    UNSAFE_OUTPUT = "unsafe_output"
    PROVENANCE_MISSING = "provenance_missing"
    RECEIPT_UNKNOWN = "receipt_unknown"
    CAPABILITY_UNVERIFIED = "capability_unverified"
    MALFORMED_TOOL_ARGUMENTS = "malformed_tool_arguments"
    EXECUTION_FAILED = "execution_failed"
    INTERNAL_ERROR = "internal_error"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    PROVIDER_RECEIPT = "provider_receipt"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"


class ToolDescriptor(BaseModel):
    """Versioned runtime descriptor; ToolCatalog is its only owner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,100}$")
    tool_version: str = Field(min_length=1, max_length=40)
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    kind: ToolKind
    input_schema_ref: str = Field(min_length=1, max_length=300)
    output_schema_ref: str = Field(min_length=1, max_length=300)
    side_effect_class: SideEffectClass
    allowed_callers: tuple[ToolCallerKind, ...]
    required_permissions: tuple[str, ...] = ()
    network_profile: str = Field(default="none", min_length=1, max_length=80)
    budget_class: str = Field(default="standard", min_length=1, max_length=80)
    default_timeout_seconds: float = Field(default=60.0, gt=0, le=1800)
    payload_limit_bytes: int = Field(default=262_144, ge=1024, le=16_777_216)
    provenance_requirements: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_callers(self) -> Self:
        if not self.allowed_callers:
            raise ValueError("a tool descriptor requires at least one allowed caller")
        if len(self.allowed_callers) != len(set(self.allowed_callers)):
            raise ValueError("allowed callers must be unique")
        return self


class ToolPolicy(BaseModel):
    """Resolved policy can only narrow the catalog descriptor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_ref: str = Field(min_length=1, max_length=300)
    allowed_tool_ids: tuple[str, ...]
    granted_permissions: tuple[str, ...] = ()
    allowed_network_profiles: tuple[str, ...] = ("none",)
    max_attempts: int = Field(default=2, ge=1, le=5)
    max_timeout_seconds: float = Field(default=120.0, gt=0, le=1800)

    def allows_tool(self, tool_id: str) -> bool:
        return tool_id in self.allowed_tool_ids


class ToolInvocationContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: str = Field(min_length=1, max_length=160)
    workspace_id: str = Field(min_length=1, max_length=160)
    command_id: str = Field(min_length=1, max_length=160)
    stage_id: str = Field(min_length=1, max_length=160)
    caller_id: str = Field(min_length=1, max_length=160)
    caller_kind: ToolCallerKind
    lease_epoch: int = Field(ge=0)
    model_id: str | None = Field(default=None, max_length=100)
    input_refs: tuple[str, ...] = ()


class ProviderToolCall(BaseModel):
    """Provider-structured call frame; never synthesized from assistant prose."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str = Field(min_length=1, max_length=200)
    tool_id: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any]


class ToolOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: str
    operation_id: str
    operation_key: str
    command_id: str
    stage_id: str
    caller_id: str
    caller_kind: ToolCallerKind
    model_id: str | None = None
    input_refs: tuple[str, ...] = ()
    tool_id: str
    tool_version: str
    descriptor_schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    args_hash: str
    policy_snapshot_ref: str
    lease_epoch: int
    attempt: int = Field(ge=1)


class ToolReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ref_id: str = Field(min_length=1, max_length=300)
    kind: str = Field(min_length=1, max_length=80)
    uri: str | None = Field(default=None, max_length=2048)
    title: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=300)
    canonical_url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=500)
    publisher: str | None = Field(default=None, max_length=300)
    authors: tuple[str, ...] = ()
    observed_at: datetime
    content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    supported_claim_refs: tuple[str, ...] = ()
    verification_status: VerificationStatus

    @field_validator("observed_at")
    @classmethod
    def _normalize_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("source observed_at must include a timezone")
        return value.astimezone(UTC)


class ToolHandlerResult(BaseModel):
    """Handler-owned fields normalized by ToolOrchestrator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ToolOutcomeStatus
    summary: str = Field(max_length=4000)
    error_type: ToolErrorType | None = None
    evidence_refs: tuple[ToolReference, ...] = ()
    source_refs: tuple[SourceReference, ...] = ()
    artifact_refs: tuple[ToolReference, ...] = ()
    confidence: float | None = Field(default=None, ge=0, le=1)
    risk_level: str = Field(default="low", max_length=40)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    recommended_next_action: str | None = Field(default=None, max_length=500)
    payload_ref: str | None = Field(default=None, max_length=1000)
    recoverable_by_model: bool = False
    retry_after_seconds: float | None = Field(default=None, ge=0, le=86_400)

    @model_validator(mode="after")
    def _validate_error_state(self) -> Self:
        if self.status is ToolOutcomeStatus.ERROR and self.error_type is None:
            raise ValueError("error outcomes require error_type")
        if self.status is not ToolOutcomeStatus.ERROR and self.error_type is not None:
            raise ValueError("only error outcomes may carry error_type")
        if (
            len(self.evidence_refs)
            + len(self.source_refs)
            + len(self.artifact_refs)
            > 96
        ):
            raise ValueError("one tool outcome may project at most 96 references")
        return self


class ResearchToolOutcome(BaseModel):
    """Canonical terminal result consumed by evidence and quality runtimes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str
    operation_key: str
    producer: str
    tool_id: str
    tool_version: str
    status: ToolOutcomeStatus
    error_type: ToolErrorType | None = None
    observed_at: datetime
    input_refs: tuple[str, ...] = ()
    summary: str = Field(max_length=2000)
    evidence_refs: tuple[ToolReference, ...] = ()
    source_refs: tuple[SourceReference, ...] = ()
    artifact_refs: tuple[ToolReference, ...] = ()
    confidence: float | None = Field(default=None, ge=0, le=1)
    risk_level: str = Field(default="low", max_length=40)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    recommended_next_action: str | None = Field(default=None, max_length=500)
    payload_ref: str | None = Field(default=None, max_length=1000)
    redaction_applied: bool = True
    recoverable_by_model: bool = False
    retry_after_seconds: float | None = Field(default=None, ge=0, le=86_400)

    @field_validator("observed_at")
    @classmethod
    def _normalize_outcome_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("outcome observed_at must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_outcome_error_state(self) -> Self:
        if self.status is ToolOutcomeStatus.ERROR and self.error_type is None:
            raise ValueError("error outcomes require error_type")
        if self.status is not ToolOutcomeStatus.ERROR and self.error_type is not None:
            raise ValueError("only error outcomes may carry error_type")
        if (
            len(self.evidence_refs)
            + len(self.source_refs)
            + len(self.artifact_refs)
            > 96
        ):
            raise ValueError("one tool outcome may project at most 96 references")
        return self


class ToolGuardDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    error_type: ToolErrorType | None = None
    user_safe_summary: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _validate_denial(self) -> Self:
        if not self.allowed and self.error_type is None:
            raise ValueError("denied guard decisions require error_type")
        return self


def utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "ProviderToolCall",
    "ResearchToolOutcome",
    "SideEffectClass",
    "SourceReference",
    "ToolCallerKind",
    "ToolDescriptor",
    "ToolErrorType",
    "ToolGuardDecision",
    "ToolHandlerResult",
    "ToolInvocationContext",
    "ToolKind",
    "ToolOperation",
    "ToolOutcomeStatus",
    "ToolPolicy",
    "ToolReference",
    "VerificationStatus",
    "utc_now",
]
