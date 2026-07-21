"""Strict model-action boundary for the single WorkspaceAgent."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from src.contracts.mission_input import (
    MISSION_INPUT_REF_PATTERN,
    MissionInputContext,
    MissionInputManifest,
)
from src.contracts.prism_context import PrismContextRef
from src.contracts.reasoning import ReasoningEffort
from src.contracts.review_policy import ReviewMode


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
    title: str = Field(min_length=1, max_length=60)
    objective: str = Field(min_length=1, max_length=20_000)
    mission_policy_id: str = Field(min_length=1, max_length=120)
    parent_mission_id: str | None = Field(default=None, max_length=36)
    initial_params: tuple[MissionInitialParameter, ...] = ()
    input_refs: tuple[str, ...] = Field(default=(), max_length=32)

    @field_validator(
        "title",
        "objective",
        "mission_policy_id",
    )
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("input_refs")
    @classmethod
    def validate_input_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("input_refs must be unique")
        if any(re.fullmatch(MISSION_INPUT_REF_PATTERN, value) is None for value in values):
            raise ValueError("input_refs must be canonical Mission input references")
        return values


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
    input_refs: tuple[str, ...] = Field(default=(), max_length=32)

    @field_validator("input_refs")
    @classmethod
    def validate_input_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("input_refs must be unique")
        if any(re.fullmatch(MISSION_INPUT_REF_PATTERN, value) is None for value in values):
            raise ValueError("input_refs must be canonical Mission input references")
        return values


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
    completion_targets: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    default_completion_target: str = Field(min_length=1, max_length=120)


class ActiveMissionContext(StrictContract):
    mission_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=60)
    objective: str = Field(min_length=1, max_length=4000)
    status: Literal["created", "planning", "running", "waiting", "completed", "failed", "cancelled"]
    active_stage_id: str | None = Field(default=None, max_length=120)
    pending_request_id: str | None = Field(default=None, max_length=160)
    pending_review_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    artifact_count: int = Field(default=0, ge=0)


class ContinuationMissionContext(StrictContract):
    mission_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=60)
    objective: str = Field(min_length=1, max_length=4000)
    status: Literal["completed", "failed", "cancelled"]
    mission_policy_id: str = Field(min_length=1, max_length=120)
    passed_stage_ids: tuple[str, ...] = Field(default=(), max_length=100)
    pinned_input_refs: tuple[str, ...] = Field(default=(), max_length=32)
    evidence_count: int = Field(default=0, ge=0)
    artifact_count: int = Field(default=0, ge=0)
    terminal_summary: str | None = Field(default=None, max_length=1000)


class WorkspaceAgentContext(StrictContract):
    workspace_id: str = Field(min_length=1, max_length=160)
    workspace_type: str = Field(min_length=1, max_length=50)
    thread_id: str = Field(min_length=1, max_length=160)
    user_id: str = Field(min_length=1, max_length=160)
    user_message_id: str = Field(min_length=1, max_length=160)
    user_message: str = Field(min_length=1, max_length=20_000)
    model_id: str = Field(min_length=1, max_length=160)
    reasoning_effort: ReasoningEffort
    model_capability_profile_hash: str = Field(min_length=8, max_length=160)
    review_mode: ReviewMode
    conversation: tuple[dict[str, Any], ...] = Field(default=(), max_length=80)
    mission_inputs: tuple[MissionInputManifest, ...] = Field(default=(), max_length=32)
    attachment_contexts: tuple[MissionInputContext, ...] = Field(default=(), max_length=32)
    policy_hints: tuple[MissionPolicyHint, ...] = Field(default=(), max_length=24)
    active_mission: ActiveMissionContext | None = None
    continuation_target: ContinuationMissionContext | None = None
    prism_context_ref: PrismContextRef | None = None

    def policy_hint(self, policy_id: str) -> MissionPolicyHint | None:
        return next((hint for hint in self.policy_hints if hint.policy_id == policy_id), None)

    def select_mission_inputs(
        self,
        input_refs: tuple[str, ...],
        *,
        include_current: bool = False,
    ) -> tuple[MissionInputManifest, ...]:
        available = {item.input_ref: item for item in self.mission_inputs}
        missing = [ref for ref in input_refs if ref not in available]
        if missing:
            raise ValueError("selected Mission input is unavailable in this conversation")
        selected_refs = list(dict.fromkeys(input_refs))
        if include_current:
            selected_refs.extend(
                context.input_ref
                for context in self.attachment_contexts
                if context.current_message
                and context.status == "ready"
                and context.input_ref in available
                and context.input_ref not in selected_refs
            )
        return tuple(available[ref] for ref in selected_refs)


AgentAction = Annotated[
    AnswerAction | AskUserAction | StartMissionAction | SteerMissionAction | ProposeReviewAction | RequestCommitAction,
    Field(discriminator="action"),
]

AgentActionAdapter: TypeAdapter[AgentAction] = TypeAdapter(AgentAction)


class WorkspaceAgentReply(StrictContract):
    text: str = Field(min_length=1)
    action: AgentAction
    mission_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
