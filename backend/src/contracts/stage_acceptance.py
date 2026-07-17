"""Versioned contracts for deterministic mission-stage acceptance."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.contracts.reasoning import ReasoningEffort
from src.contracts.research_evidence import (
    ArtifactRecord,
    EvidenceRecord,
    ResearchSurface,
)
from src.contracts.versioned import (
    ImmutableContentRef,
    ImmutableContractRef,
    contract_sha256,
)

WorkspaceType = Literal[
    "sci",
    "thesis",
    "proposal",
    "software_copyright",
    "math_modeling",
    "patent",
]
StageDecision = Literal["pass", "revise", "ask_user", "stop"]
CriterionStatus = Literal["pass", "fail", "unknown"]
ExemplarVerdict = Literal["below", "meets", "exceeds", "not_compared"]
FailureAction = Literal[
    "revise_existing",
    "retrieve_more_evidence",
    "ask_user",
    "degrade_with_notice",
    "stop_execution",
]


class StageInstantiationRule(BaseModel):
    """Resolve a quality-contract family into concrete sequential stage ids."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["single", "per_item"] = "single"
    source_context_key: str | None = None
    instance_id_template: str | None = None
    same_item_prerequisite_templates: tuple[str, ...] = ()
    previous_item_prerequisite_templates: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_instantiation(self) -> StageInstantiationRule:
        templates = (
            *((self.instance_id_template,) if self.instance_id_template else ()),
            *self.same_item_prerequisite_templates,
            *self.previous_item_prerequisite_templates,
        )
        if self.mode == "single":
            if self.source_context_key or templates:
                raise ValueError("single stage instantiation cannot declare item templates")
            return self
        if not str(self.source_context_key or "").strip():
            raise ValueError("per_item stage instantiation requires source_context_key")
        if not str(self.instance_id_template or "").strip():
            raise ValueError("per_item stage instantiation requires instance_id_template")
        if any(template.count("{index}") != 1 for template in templates):
            raise ValueError("per_item stage templates must contain {index} exactly once")
        return self


class ResolvedStageInstance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage_id: str
    contract_stage_id: str
    sequence_index: int | None = Field(default=None, ge=1)
    prerequisite_stage_ids: tuple[str, ...] = ()


class StageCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    criterion_id: str
    description: str
    required_evidence_surfaces: tuple[ResearchSurface, ...] = ()
    requires_supporting_ref: bool = True

    @field_validator("criterion_id", "description")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("criterion id and description must be non-empty")
        return value


class ArtifactRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    minimum_count: int = Field(default=1, ge=1, le=20)
    requires_manifest: bool = False

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("artifact requirement kind must be non-empty")
        return value


class StageAcceptanceContract(BaseModel):
    """Data contract stating what a stage must achieve, never how to execute it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["stage_acceptance_contract.v2"]
    contract_id: str
    version: int = Field(ge=1)
    mission_policy_id: str
    workspace_type: WorkspaceType
    stage_id: str
    stage_goal: str
    minimum_criteria: tuple[StageCriterion, ...]
    excellent_criteria: tuple[StageCriterion, ...] = ()
    required_evidence_surfaces: tuple[ResearchSurface, ...] = ()
    required_artifacts: tuple[ArtifactRequirement, ...] = ()
    failure_modes: tuple[str, ...] = ()
    allowed_actions_if_failed: tuple[FailureAction, ...]
    max_revision_attempts: int = Field(default=3, ge=0, le=12)
    no_progress_limit: int = Field(default=2, ge=1, le=6)
    recommended_model_effort: ReasoningEffort = ReasoningEffort.HIGH
    prerequisite_stage_ids: tuple[str, ...] = ()
    instantiation: StageInstantiationRule = Field(default_factory=StageInstantiationRule)
    all_item_prerequisite_templates: tuple[str, ...] = ()
    all_item_source_context_key: str | None = None
    advance_condition: str
    stop_condition: str
    exemplar_refs: tuple[ImmutableContentRef, ...] = ()
    require_exemplar_comparison: bool = False
    anti_examples: tuple[str, ...] = ()

    @field_validator(
        "contract_id",
        "mission_policy_id",
        "stage_id",
        "stage_goal",
        "advance_condition",
        "stop_condition",
    )
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("stage contract identifiers and conditions must be non-empty")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> StageAcceptanceContract:
        if not self.minimum_criteria:
            raise ValueError("minimum_criteria must not be empty")
        criterion_ids = [criterion.criterion_id for criterion in (*self.minimum_criteria, *self.excellent_criteria)]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("criterion ids must be unique within a stage contract")
        if "stop_execution" not in self.allowed_actions_if_failed:
            raise ValueError("allowed_actions_if_failed must include stop_execution")
        if "revise_existing" not in self.allowed_actions_if_failed:
            raise ValueError("allowed_actions_if_failed must include revise_existing")
        if self.require_exemplar_comparison and not self.exemplar_refs:
            raise ValueError("exemplar comparison requires at least one exemplar ref")
        if self.stage_id in self.prerequisite_stage_ids:
            raise ValueError("a stage cannot depend on itself")
        if any(template.count("{index}") != 1 for template in self.all_item_prerequisite_templates):
            raise ValueError("all-item prerequisite templates must contain {index} exactly once")
        all_item_source = str(self.all_item_source_context_key or "").strip()
        if self.all_item_prerequisite_templates and not all_item_source:
            raise ValueError(
                "all-item prerequisites require all_item_source_context_key"
            )
        if all_item_source and not self.all_item_prerequisite_templates:
            raise ValueError(
                "all_item_source_context_key requires all-item prerequisites"
            )
        instance_source = str(self.instantiation.source_context_key or "").strip()
        if instance_source and all_item_source and instance_source != all_item_source:
            raise ValueError(
                "stage prerequisite families must use one item-count source"
            )
        unique_groups = {
            "prerequisite_stage_ids": self.prerequisite_stage_ids,
            "required_artifact_kinds": tuple(item.kind for item in self.required_artifacts),
            "exemplar_refs": tuple(item.ref_id for item in self.exemplar_refs),
        }
        for label, values in unique_groups.items():
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must not contain duplicates")
        return self

    def item_count_source_key(self) -> str | None:
        """Return the single pinned count source used to resolve this stage."""

        return self.instantiation.source_context_key or self.all_item_source_context_key

    def acceptance_criteria(self) -> tuple[StageCriterion, ...]:
        """Return every criterion that must pass before stage progression."""

        return (*self.minimum_criteria, *self.excellent_criteria)

    def immutable_ref(self) -> ImmutableContractRef:
        return ImmutableContractRef(
            contract_id=self.contract_id,
            schema_version=self.schema_version,
            sha256=contract_sha256(self),
        )


def stage_instance_index(
    template: str | None,
    stage_id: str,
) -> int | None:
    """Return the canonical one-based index encoded by a stage instance id."""

    if not template or template.count("{index}") != 1:
        return None
    prefix, suffix = template.split("{index}")
    if not stage_id.startswith(prefix) or not stage_id.endswith(suffix):
        return None
    end = len(stage_id) - len(suffix) if suffix else len(stage_id)
    encoded_index = stage_id[len(prefix) : end]
    if not encoded_index.isascii() or not encoded_index.isdecimal():
        return None
    index = int(encoded_index)
    if index < 1 or encoded_index != str(index):
        return None
    return index


def format_stage_instance_id(template: str | None, index: int) -> str:
    """Build the canonical one-based id for a per-item stage template."""

    if not template or template.count("{index}") != 1:
        raise ValueError("stage instance template must contain {index} exactly once")
    if index < 1:
        raise ValueError("stage instance index must be positive")
    return template.replace("{index}", str(index))


def stage_id_matches_contract(
    contract: StageAcceptanceContract,
    stage_id: str,
) -> bool:
    """Determine whether an executable stage id belongs to a pinned contract."""

    if contract.instantiation.mode == "single":
        return stage_id == contract.stage_id
    return stage_instance_index(
        contract.instantiation.instance_id_template,
        stage_id,
    ) is not None


class CriterionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    criterion_id: str
    status: CriterionStatus
    supporting_refs: tuple[str, ...] = ()
    rationale: str = Field(min_length=20, max_length=4000)

    @field_validator("criterion_id", "rationale")
    @classmethod
    def validate_assessment_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("criterion assessment text must be non-empty")
        return value


class ExemplarComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    exemplar_ref_id: str
    verdict: ExemplarVerdict
    criterion_ids: tuple[str, ...] = ()
    note: str = ""


class StageProgressState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_count: int = Field(default=0, ge=0)
    revision_count: int = Field(default=0, ge=0)
    no_progress_count: int = Field(default=0, ge=0)
    last_attempt_item_seq: int | None = Field(default=None, ge=1)
    last_passed_item_seq: int | None = Field(default=None, ge=1)
    last_failure_fingerprint: str | None = None
    last_failed_criteria: tuple[str, ...] = ()
    next_repair_action: FailureAction | None = None


class StageAssessmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage_id: str
    contract_stage_id: str | None = None
    sequence_index: int | None = Field(default=None, ge=1)
    operation_id: str
    criterion_assessments: tuple[CriterionAssessment, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    artifacts: tuple[ArtifactRecord, ...] = ()
    exemplar_comparisons: tuple[ExemplarComparison, ...] = ()
    blocking_user_inputs: tuple[str, ...] = ()
    partial_output_refs: tuple[str, ...] = ()
    actual_model_effort: ReasoningEffort
    item_seq: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_unique_assessment_ids(self) -> StageAssessmentInput:
        groups = {
            "criterion assessments": tuple(item.criterion_id for item in self.criterion_assessments),
            "exemplar comparisons": tuple(item.exemplar_ref_id for item in self.exemplar_comparisons),
            "artifacts": tuple(item.artifact_id for item in self.artifacts),
        }
        for label, values in groups.items():
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} are not allowed")
        evidence_surfaces = tuple((item.evidence_id, item.surface) for item in self.evidence)
        if len(evidence_surfaces) != len(set(evidence_surfaces)):
            raise ValueError("duplicate evidence surfaces are not allowed")
        return self


class StageAcceptanceResult(BaseModel):
    """Canonical quality_check MissionItem payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_ref: ImmutableContractRef
    stage_id: str
    contract_stage_id: str
    sequence_index: int | None = None
    operation_id: str
    result: StageDecision
    satisfied_criteria: tuple[str, ...] = ()
    missing_criteria: tuple[str, ...] = ()
    missing_evidence_surfaces: tuple[ResearchSurface, ...] = ()
    missing_artifact_kinds: tuple[str, ...] = ()
    missing_exemplar_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    blocking_user_inputs: tuple[str, ...] = ()
    partial_output_refs: tuple[str, ...] = ()
    next_action: FailureAction | None = None
    failure_fingerprint: str | None = None
    progress_state: StageProgressState

    def to_mission_item_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude_none=True)
