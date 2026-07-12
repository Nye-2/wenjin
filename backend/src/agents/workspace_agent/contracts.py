"""Strict model-action boundary for the single WorkspaceAgent."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from src.dataservice_client.contracts.mission import MissionReviewMode


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MissionInputKind(StrEnum):
    STEER = "steer"
    CONTEXT = "context"
    CORRECTION = "correction"
    PAUSE = "pause"
    CANCEL = "cancel"
    REVIEW = "review"
    ADVISORY = "advisory"


class MissionInitialParameter(StrictContract):
    key: str = Field(min_length=1, max_length=120)
    value: str = Field(max_length=8000)


class MissionStartSpec(StrictContract):
    workspace_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    workspace_type: str = Field(min_length=1)
    raw_user_message_id: str = Field(min_length=1)
    mission_idempotency_key: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=20_000)
    mission_policy_id: str = Field(min_length=1, max_length=120)
    initial_params: tuple[MissionInitialParameter, ...] = ()
    review_mode: MissionReviewMode = MissionReviewMode.BALANCED_DEFAULT
    model_id: str = Field(min_length=1, max_length=160)
    reasoning_effort: Literal["low", "medium", "high", "xhigh"]
    model_capability_profile_hash: str = Field(min_length=8, max_length=160)
    runtime_context_refs: tuple[str, ...] = ()

    @field_validator(
        "workspace_id",
        "thread_id",
        "user_id",
        "workspace_type",
        "raw_user_message_id",
        "mission_idempotency_key",
        "objective",
        "mission_policy_id",
        "model_id",
        "model_capability_profile_hash",
    )
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class AnswerAction(StrictContract):
    action: Literal["answer"] = "answer"
    text: str = Field(min_length=1)


class AskUserAction(StrictContract):
    action: Literal["ask_user"] = "ask_user"
    request_id: str = Field(min_length=1, max_length=160)
    question: str = Field(min_length=1, max_length=4000)
    choices: tuple[str, ...] = ()


class StartMissionAction(StrictContract):
    action: Literal["start_mission"] = "start_mission"
    mission: MissionStartSpec


class SteerMissionAction(StrictContract):
    action: Literal["steer_mission"] = "steer_mission"
    mission_id: str = Field(min_length=1, max_length=160)
    command_id: str = Field(min_length=1, max_length=200)
    input_kind: MissionInputKind
    instruction: str = Field(min_length=1, max_length=8000)
    request_id: str | None = Field(default=None, max_length=160)


class ProposeReviewAction(StrictContract):
    action: Literal["propose_review"] = "propose_review"
    mission_id: str = Field(min_length=1, max_length=160)
    review_item_ids: tuple[str, ...] = Field(min_length=1)
    decision: Literal["accept", "reject", "needs_more_evidence"]
    rationale: str | None = Field(default=None, max_length=4000)


class RequestCommitAction(StrictContract):
    action: Literal["request_commit"] = "request_commit"
    mission_id: str = Field(min_length=1, max_length=160)
    review_item_ids: tuple[str, ...] = Field(min_length=1)


class MissionPolicyHint(StrictContract):
    policy_id: str = Field(min_length=1, max_length=120)
    content_hash: str = Field(min_length=64, max_length=64)
    display_name: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=600)
    positive_examples: tuple[str, ...] = Field(default=(), max_length=4)
    negative_examples: tuple[str, ...] = Field(default=(), max_length=4)
    required_context: tuple[str, ...] = Field(default=(), max_length=8)


class ActiveMissionContext(StrictContract):
    mission_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1, max_length=4000)
    status: Literal["created", "planning", "running", "waiting", "completed", "failed", "cancelled"]
    active_stage_id: str | None = Field(default=None, max_length=120)
    pending_request_id: str | None = Field(default=None, max_length=160)
    pending_review_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    artifact_count: int = Field(default=0, ge=0)


class WorkspaceAgentContext(StrictContract):
    workspace_id: str = Field(min_length=1, max_length=160)
    workspace_type: str = Field(min_length=1, max_length=50)
    thread_id: str = Field(min_length=1, max_length=160)
    user_id: str = Field(min_length=1, max_length=160)
    user_message_id: str = Field(min_length=1, max_length=160)
    user_message: str = Field(min_length=1, max_length=20_000)
    model_id: str = Field(min_length=1, max_length=160)
    reasoning_effort: Literal["low", "medium", "high", "xhigh"]
    model_capability_profile_hash: str = Field(min_length=8, max_length=160)
    conversation: tuple[dict[str, Any], ...] = Field(default=(), max_length=80)
    policy_hints: tuple[MissionPolicyHint, ...] = Field(default=(), max_length=24)
    active_mission: ActiveMissionContext | None = None

    def policy_hint(self, policy_id: str) -> MissionPolicyHint | None:
        return next((hint for hint in self.policy_hints if hint.policy_id == policy_id), None)


AgentAction = Annotated[
    AnswerAction
    | AskUserAction
    | StartMissionAction
    | SteerMissionAction
    | ProposeReviewAction
    | RequestCommitAction,
    Field(discriminator="action"),
]

AgentActionAdapter: TypeAdapter[AgentAction] = TypeAdapter(AgentAction)


class WorkspaceAgentReply(StrictContract):
    text: str = Field(min_length=1)
    action: AgentAction
    mission_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
