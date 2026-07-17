"""Lightweight MissionPolicy and WorkerSkill contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.contracts.mission_budget import MissionExecutionBudget
from src.contracts.research_evidence import (
    NON_BYPASSABLE_REVIEW_RISKS,
    ReviewRiskCategory,
)
from src.contracts.review_policy import ReviewMode
from src.contracts.stage_acceptance import WorkspaceType
from src.contracts.versioned import ImmutableContractRef, contract_sha256

PolicyVisibility = Literal["route_hint", "internal"]


def _open_object_schema_paths(schema: object, *, path: str = "output_contract") -> list[str]:
    if isinstance(schema, list):
        findings: list[str] = []
        for index, value in enumerate(schema):
            findings.extend(_open_object_schema_paths(value, path=f"{path}[{index}]"))
        return findings
    if not isinstance(schema, dict):
        return []
    findings = []
    if schema.get("type") == "object":
        properties = schema.get("properties")
        if not isinstance(properties, dict) or not properties:
            findings.append(path)
    for key, value in schema.items():
        findings.extend(_open_object_schema_paths(value, path=f"{path}.{key}"))
    return findings


class MissionPolicyDisplay(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str


class MissionRoutingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    when_to_use: tuple[str, ...]
    not_for: tuple[str, ...]
    positive_examples: tuple[str, ...]
    negative_examples: tuple[str, ...]


class MinimumContextRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement: Literal["required", "optional"]
    ask: str | None = None

    @model_validator(mode="after")
    def require_question_for_required_context(self) -> MinimumContextRequirement:
        if self.requirement == "required" and not str(self.ask or "").strip():
            raise ValueError("required minimum context must provide an ask prompt")
        return self


class MissionGoal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: str
    target_outcomes: tuple[str, ...]
    hard_constraints: tuple[str, ...]
    forbidden_outcomes: tuple[str, ...] = ()


class ToolPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_tool_groups: tuple[str, ...]
    denied_tools: tuple[str, ...] = ()


class ReviewPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    default_mode: ReviewMode = ReviewMode.BALANCED_DEFAULT
    allowed_modes: tuple[ReviewMode, ...] = (
        ReviewMode.REVIEW_ALL,
        ReviewMode.BALANCED_DEFAULT,
        ReviewMode.AUTO_DRAFT,
    )
    non_bypassable_risks: tuple[ReviewRiskCategory, ...]

    @model_validator(mode="after")
    def preserve_non_bypassable_academic_review(self) -> ReviewPolicy:
        if self.default_mode not in self.allowed_modes:
            raise ValueError("default review mode must be allowed")
        missing = NON_BYPASSABLE_REVIEW_RISKS - set(self.non_bypassable_risks)
        if missing:
            raise ValueError("review policy cannot bypass academic trust risks: " + ", ".join(sorted(missing)))
        return self

    def require_allowed_mode(self, mode: ReviewMode) -> ReviewMode:
        """Return a normalized mode only when this pinned policy permits it."""

        normalized = ReviewMode(mode)
        if normalized not in self.allowed_modes:
            raise ValueError(
                f"Review mode {normalized.value!r} is not allowed by the pinned MissionPolicy"
            )
        return normalized


class VersionedPolicyRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str
    version: int = Field(ge=1)


class MissionExample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    example_id: str
    input_summary: str
    expected_characteristics: tuple[str, ...]

    def content_hash(self) -> str:
        return contract_sha256(self)


class MissionAntiExample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str
    failure_reason: str


class CompletionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage_ids: tuple[str, ...] = Field(min_length=1)
    terminal_output_kinds: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_values(self) -> CompletionTarget:
        if len(self.stage_ids) != len(set(self.stage_ids)):
            raise ValueError("completion target stage_ids must be unique")
        if len(self.terminal_output_kinds) != len(set(self.terminal_output_kinds)):
            raise ValueError("completion target terminal_output_kinds must be unique")
        return self


class CompletionContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    default_target: str
    targets: dict[str, CompletionTarget]
    allow_safe_partial_outputs: bool = True

    @model_validator(mode="after")
    def validate_targets(self) -> CompletionContract:
        if self.default_target not in self.targets:
            raise ValueError("completion default_target must exist in targets")
        if not self.targets:
            raise ValueError("completion contract requires at least one target")
        return self


class DeliveryProfileRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str
    version: int = Field(ge=1)


class MissionPolicy(BaseModel):
    """Strict outer policy around a model-directed mission loop."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["mission_policy.v1"]
    id: str
    version: int = Field(ge=1)
    workspace_type: WorkspaceType
    enabled: bool = True
    visibility: PolicyVisibility = "route_hint"
    display: MissionPolicyDisplay
    routing: MissionRoutingPolicy
    mission: MissionGoal
    execution_budget: MissionExecutionBudget
    minimum_context: dict[str, MinimumContextRequirement]
    stage_contract_refs: tuple[ImmutableContractRef, ...]
    tool_policy: ToolPolicy
    allowed_worker_skills: tuple[str, ...]
    review_policy: ReviewPolicy
    sandbox_policy_ref: VersionedPolicyRef
    examples: tuple[MissionExample, ...]
    anti_examples: tuple[MissionAntiExample, ...]
    completion_contract: CompletionContract
    delivery_profile_refs: tuple[DeliveryProfileRef, ...] = ()

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("mission policy id is required")
        return value

    @model_validator(mode="after")
    def validate_policy(self) -> MissionPolicy:
        if not self.stage_contract_refs:
            raise ValueError("mission policy requires stage_contract_refs")
        contract_ids = [ref.contract_id for ref in self.stage_contract_refs]
        if len(contract_ids) != len(set(contract_ids)):
            raise ValueError("stage contract refs must be unique")
        if not self.allowed_worker_skills:
            raise ValueError("mission policy requires at least one allowed worker skill")
        if len(self.allowed_worker_skills) != len(set(self.allowed_worker_skills)):
            raise ValueError("allowed worker skills must be unique")
        if not self.examples or not self.anti_examples:
            raise ValueError("mission policy requires excellent and anti examples")
        example_ids = tuple(example.example_id for example in self.examples)
        if len(example_ids) != len(set(example_ids)):
            raise ValueError("mission policy example ids must be unique")
        if self.visibility == "route_hint":
            if len(self.routing.positive_examples) < 3:
                raise ValueError("route_hint policy requires at least three positive examples")
            if len(self.routing.negative_examples) < 3:
                raise ValueError("route_hint policy requires at least three negative examples")
            if not any(item.requirement == "required" for item in self.minimum_context.values()):
                raise ValueError("route_hint policy requires at least one required context field")
        return self

    def immutable_ref(self) -> ImmutableContractRef:
        return ImmutableContractRef(
            contract_id=self.id,
            schema_version=self.schema_version,
            sha256=contract_sha256(self),
        )

    def to_catalog_data(
        self,
        *,
        resolved_stage_contracts: list[dict[str, object]],
    ) -> dict[str, object]:
        data = self.model_dump(mode="json", exclude_none=True)
        return {
            **data,
            "resolved_stage_contracts": resolved_stage_contracts,
            "content_hash": self.immutable_ref().sha256,
        }


class WorkerSkillExample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task: str
    strong_output_characteristics: tuple[str, ...]


class WorkerSkill(BaseModel):
    """Bounded worker guidance; stage lifecycle remains owned by the runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["worker_skill.v1"]
    id: str
    version: int = Field(ge=1)
    enabled: bool = True
    role_hint: str
    instructions: tuple[str, ...]
    allowed_tool_groups: tuple[str, ...] = ()
    input_contract: dict[str, object]
    output_contract: dict[str, object]
    quality_focus: tuple[str, ...]
    examples: tuple[WorkerSkillExample, ...]

    @field_validator("id", "role_hint")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("worker skill id and role_hint must be non-empty")
        return value

    @model_validator(mode="after")
    def validate_bounded_skill(self) -> WorkerSkill:
        if not self.instructions or len(self.instructions) > 12:
            raise ValueError("worker skill instructions must contain 1 to 12 bounded items")
        if sum(len(item) for item in self.instructions) > 6000:
            raise ValueError("worker skill instructions exceed bounded context budget")
        if any(not item.strip() for item in self.instructions):
            raise ValueError("worker skill instructions must not contain blank items")
        if self.input_contract.get("type") != "object":
            raise ValueError("input_contract must declare type=object")
        if self.output_contract.get("type") != "object":
            raise ValueError("output_contract must declare type=object")
        required = set(self.output_contract.get("required") or [])
        baseline = {"summary", "evidence_refs", "artifact_refs", "warnings"}
        if not baseline <= required:
            raise ValueError("output_contract must require summary, evidence_refs, artifact_refs, and warnings")
        properties = self.output_contract.get("properties")
        artifact_refs = properties.get("artifact_refs") if isinstance(properties, dict) else None
        if (
            isinstance(artifact_refs, dict)
            and int(artifact_refs.get("minItems") or 0) > 0
            and "artifact_render" not in self.allowed_tool_groups
        ):
            raise ValueError("worker skills that require artifact refs must allow artifact_render")
        open_paths = _open_object_schema_paths(self.output_contract)
        if open_paths:
            raise ValueError("output_contract contains open object schema(s): " + ", ".join(open_paths[:8]))
        if not self.quality_focus or not self.examples:
            raise ValueError("worker skills require quality focus and at least one example")
        return self

    def immutable_ref(self) -> ImmutableContractRef:
        return ImmutableContractRef(
            contract_id=self.id,
            schema_version=self.schema_version,
            sha256=contract_sha256(self),
        )

    def to_catalog_data(self) -> dict[str, object]:
        return {
            **self.model_dump(mode="json", exclude_none=True),
            "content_hash": self.immutable_ref().sha256,
        }
