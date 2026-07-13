"""Contracts for research figure generation specs and artifacts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from src.sandbox.workspace_layout import (
    is_user_reviewable_workspace_artifact_path,
    is_workspace_internal_path,
    is_workspace_protected_path,
    normalize_workspace_virtual_path,
)

FigureType = Literal[
    "data_plot",
    "experiment_plot",
    "statistical_chart",
    "architecture_diagram",
    "method_flow",
    "mechanism_illustration",
    "conceptual_illustration",
    "experimental_setup_illustration",
    "graphical_abstract",
    "academic_cover",
    "educational_explainer",
    "patent_drawing",
    "table_visual",
    "geometric_schematic",
    "simulation_snapshot",
    "other",
]

FigureStrategy = Literal[
    "matplotlib",
    "seaborn",
    "graphviz",
    "llm_image",
    "hybrid",
    "python_schematic",
]

EvidenceLevel = Literal["evidence", "explanatory", "decorative"]
BriefStatement = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
VisualSourceRef = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2048)]
ForbiddenVisualElement = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
VisualLabelAnchor = Literal[
    "top_left",
    "top_center",
    "top_right",
    "center_left",
    "center",
    "center_right",
    "bottom_left",
    "bottom_center",
    "bottom_right",
]

CHART_CODE_STRATEGIES = frozenset({"matplotlib", "seaborn"})
CODE_REQUIRED_TYPES = frozenset({"data_plot", "experiment_plot", "statistical_chart", "table_visual"})
STRUCTURED_REQUIRED_TYPES = frozenset({"architecture_diagram", "method_flow", "patent_drawing"})
STRUCTURED_STRATEGIES = frozenset({"graphviz"})
AI_IMAGE_STRATEGIES = frozenset({"llm_image", "hybrid"})
GENERATIVE_FIGURE_TYPES = frozenset(
    {
        "conceptual_illustration",
        "mechanism_illustration",
        "experimental_setup_illustration",
        "graphical_abstract",
        "academic_cover",
        "educational_explainer",
    }
)
SCHEMATIC_TYPES = frozenset({"geometric_schematic", "simulation_snapshot"})
SCHEMATIC_STRATEGIES = frozenset({"python_schematic"})


def _validate_figure_route(
    *,
    figure_type: FigureType,
    strategy: FigureStrategy,
    evidence_level: EvidenceLevel,
) -> None:
    if evidence_level == "evidence" and strategy in AI_IMAGE_STRATEGIES:
        raise ValueError("evidence figures cannot use AI image generation strategies")
    if figure_type in CODE_REQUIRED_TYPES and strategy not in CHART_CODE_STRATEGIES:
        if strategy in AI_IMAGE_STRATEGIES:
            raise ValueError("data figures must use code generation strategies")
        raise ValueError("data figures must use chart code generation strategies")
    if figure_type in STRUCTURED_REQUIRED_TYPES and strategy not in STRUCTURED_STRATEGIES:
        raise ValueError("structured figures must use structured diagram strategies")
    if figure_type in SCHEMATIC_TYPES and strategy not in SCHEMATIC_STRATEGIES:
        raise ValueError("schematic and simulation figures must use python_schematic")
    if strategy in AI_IMAGE_STRATEGIES and figure_type not in GENERATIVE_FIGURE_TYPES:
        raise ValueError("AI image strategies are limited to generative figure types")
    if figure_type in GENERATIVE_FIGURE_TYPES and strategy not in AI_IMAGE_STRATEGIES:
        raise ValueError("generative figure types require llm_image or hybrid")


class ExactVisualLabel(BaseModel):
    """Text that must be rendered exactly by a deterministic overlay."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=500)
    semantic_anchor: VisualLabelAnchor
    importance: Literal["required", "optional"] = "required"


class PrismContextRef(BaseModel):
    """Hash-bound Prism selection used to assemble academic visual context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=120)
    prism_project_id: str = Field(min_length=1, max_length=120)
    file_id: str = Field(min_length=1, max_length=120)
    base_revision_ref: str = Field(min_length=1, max_length=2048)
    selection_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    selection_range: tuple[int, int]

    @field_validator("selection_range")
    @classmethod
    def _validate_selection_locator(cls, value: tuple[int, int]) -> tuple[int, int]:
        start, end = value
        if start < 0 or end <= start:
            raise ValueError("selection_range must be a non-empty forward range")
        return value


class FigureSpec(BaseModel):
    """Requested figure generation plan emitted by an agent."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["wenjin.figure_generation.spec.v1"] = Field(
        default="wenjin.figure_generation.spec.v1",
        alias="schema",
    )
    figure_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    figure_type: FigureType
    strategy: FigureStrategy
    evidence_level: EvidenceLevel = "explanatory"
    visual_profile_id: str | None = Field(default=None, max_length=120)
    palette_id: str | None = Field(default=None, max_length=120)
    purpose: str = Field(min_length=1, max_length=1000)
    output_targets: list[str] = Field(default_factory=list, max_length=4)
    caption: str | None = Field(default=None, max_length=4000)
    alt_text: str | None = Field(default=None, max_length=4000)
    dataset_paths: list[str] = Field(default_factory=list, max_length=64)

    @property
    def schema(self) -> str:
        return self.schema_

    @field_validator("output_targets")
    @classmethod
    def _normalize_output_targets(cls, paths: list[str]) -> list[str]:
        return [_normalize_workspace_path(path, error_message="reviewable workspace artifact") for path in paths]

    @field_validator("dataset_paths")
    @classmethod
    def _validate_dataset_paths(cls, paths: list[str]) -> list[str]:
        return [_ensure_safe_workspace_path(path) for path in paths]

    @model_validator(mode="after")
    def _validate_strategy_and_targets(self) -> FigureSpec:
        _validate_figure_route(
            figure_type=self.figure_type,
            strategy=self.strategy,
            evidence_level=self.evidence_level,
        )
        for path in self.output_targets:
            _ensure_reviewable_workspace_artifact(path, field_name="output target")
        return self


class AcademicFigureBrief(BaseModel):
    """Bounded academic intent and authoritative references for one visual."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["wenjin.academic_visual.brief.v1"] = Field(
        default="wenjin.academic_visual.brief.v1",
        alias="schema",
    )
    figure_spec: FigureSpec
    intended_use: Literal["manuscript", "presentation", "cover", "workspace"]
    audience: str = Field(min_length=1, max_length=500)
    target_language: str = Field(min_length=1, max_length=80)
    aspect_ratio: Literal["1:1", "4:3", "3:2", "16:9", "portrait"]
    composition: str = Field(min_length=1, max_length=2000)
    scientific_invariants: tuple[BriefStatement, ...] = Field(default=(), max_length=32)
    exact_labels: tuple[ExactVisualLabel, ...] = Field(default=(), max_length=32)
    source_refs: tuple[VisualSourceRef, ...] = Field(default=(), max_length=128)
    forbidden_elements: tuple[ForbiddenVisualElement, ...] = Field(default=(), max_length=32)
    prism_context_ref: PrismContextRef | None = None

    @property
    def schema(self) -> str:
        return self.schema_

    @model_validator(mode="after")
    def _validate_exact_label_strategy(self) -> AcademicFigureBrief:
        if self.exact_labels and self.figure_spec.figure_type in GENERATIVE_FIGURE_TYPES and self.figure_spec.strategy != "hybrid":
            raise ValueError("generative figures with exact labels require hybrid strategy")
        return self


class CodeVisualPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["code"] = "code"
    source_code: str = Field(min_length=1, max_length=200_000)
    script_path: str
    environment_id: str | None = Field(default=None, min_length=1, max_length=100)
    dataset_paths: tuple[str, ...] = ()

    @field_validator("script_path")
    @classmethod
    def _validate_script_path(cls, path: str) -> str:
        return _ensure_safe_workspace_path(path)

    @field_validator("dataset_paths")
    @classmethod
    def _validate_dataset_paths(cls, paths: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_ensure_safe_workspace_path(path) for path in paths)


class StructuredVisualPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["structured"] = "structured"
    source: str = Field(min_length=1, max_length=200_000)
    output_format: Literal["svg", "pdf", "png"]


class GenerativeVisualPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["generative"] = "generative"
    quality: Literal["low", "medium", "high", "auto"] = "high"
    size: Literal["1024x1024", "1536x1024", "1024x1536"]


VisualRenderPayload = Annotated[
    CodeVisualPayload | StructuredVisualPayload | GenerativeVisualPayload,
    Field(discriminator="kind"),
]


class AcademicVisualRenderInput(BaseModel):
    """Strategy-bound request accepted by the future canonical visual tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    brief: AcademicFigureBrief
    render: VisualRenderPayload

    @model_validator(mode="after")
    def _validate_render_strategy(self) -> AcademicVisualRenderInput:
        strategy = self.brief.figure_spec.strategy
        expected_kind = _render_kind_for_strategy(strategy)
        if self.render.kind != expected_kind:
            raise ValueError(f"strategy {strategy} requires {expected_kind} render payload")
        return self


class AcademicVisualCandidate(BaseModel):
    """Unified staged result from a deterministic, real-artifact, or image route."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True, frozen=True)

    schema_: Literal["wenjin.academic_visual.candidate.v1"] = Field(
        default="wenjin.academic_visual.candidate.v1",
        alias="schema",
    )
    candidate_id: str = Field(min_length=1, max_length=120)
    figure_id: str = Field(min_length=1, max_length=120)
    figure_type: FigureType
    strategy: FigureStrategy
    evidence_level: EvidenceLevel
    preview_ref: str | None = Field(default=None, min_length=1, max_length=2048)
    sandbox_artifact_ref: str | None = Field(default=None, min_length=1, max_length=2048)
    review_preview_ref: str = Field(min_length=1, max_length=2048)
    preview_hash: str = Field(min_length=1, max_length=256)
    content_hash: str = Field(min_length=1, max_length=256)
    mime_type: Literal["image/png", "image/webp", "image/svg+xml", "application/pdf"]
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    renderer_id: str = Field(min_length=1, max_length=120)
    renderer_version: str = Field(min_length=1, max_length=120)
    provider_model: Literal["gpt-image-2"] | None = None
    source_code_hash: str | None = Field(default=None, min_length=1, max_length=256)
    source_prompt_hash: str | None = Field(default=None, min_length=1, max_length=256)
    context_hash: str = Field(min_length=1, max_length=256)
    source_refs: tuple[str, ...] = ()
    dataset_refs: tuple[str, ...] = ()
    reproducibility_ref: str | None = Field(default=None, min_length=1, max_length=2048)
    quality_receipt: dict[str, object] = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def schema(self) -> str:
        return self.schema_

    @model_validator(mode="after")
    def _validate_primary_candidate_and_provider(self) -> AcademicVisualCandidate:
        _validate_figure_route(
            figure_type=self.figure_type,
            strategy=self.strategy,
            evidence_level=self.evidence_level,
        )
        primary_refs = (self.preview_ref, self.sandbox_artifact_ref)
        if sum(ref is not None for ref in primary_refs) != 1:
            raise ValueError("candidate requires exactly one primary candidate ref")
        if self.strategy in AI_IMAGE_STRATEGIES:
            if self.provider_model != "gpt-image-2":
                raise ValueError("AI image candidates require provider_model gpt-image-2")
            if self.preview_ref is None:
                raise ValueError("AI image candidates require a transient preview ref")
            if self.review_preview_ref != self.preview_ref:
                raise ValueError("AI image candidate preview refs must identify the same transient object")
        elif self.provider_model is not None:
            raise ValueError("deterministic and real-artifact candidates cannot declare provider_model")
        if self.strategy not in AI_IMAGE_STRATEGIES and self.sandbox_artifact_ref is None:
            raise ValueError("deterministic candidates require sandbox_artifact_ref")
        return self


class VisualCandidateRef(BaseModel):
    """Content-bound location of candidate bytes before MissionCommit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["sandbox_artifact", "transient_preview"]
    ref: str = Field(min_length=1, max_length=2048)
    content_hash: str = Field(min_length=1, max_length=256)


class FigureArtifactManifest(BaseModel):
    """Manifest for a generated figure artifact staged for review."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True, frozen=True)

    schema_: Literal["wenjin.figure_generation.artifact.v2"] = Field(
        default="wenjin.figure_generation.artifact.v2",
        alias="schema",
    )
    figure_id: str = Field(min_length=1, max_length=120)
    figure_type: FigureType
    strategy: FigureStrategy
    evidence_level: EvidenceLevel
    candidate: VisualCandidateRef
    intended_output_targets: tuple[str, ...] = ()
    renderer_id: str = Field(min_length=1, max_length=120)
    renderer_version: str = Field(min_length=1, max_length=120)
    source_code_ref: str | None = Field(default=None, min_length=1, max_length=2048)
    source_prompt_hash: str | None = Field(default=None, min_length=1, max_length=256)
    dataset_refs: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    reproducibility_ref: str | None = Field(default=None, min_length=1, max_length=2048)
    caption: str | None = Field(default=None, max_length=4000)
    alt_text: str | None = Field(default=None, max_length=4000)

    @property
    def schema(self) -> str:
        return self.schema_

    @field_validator("intended_output_targets")
    @classmethod
    def _validate_intended_output_targets(cls, paths: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_normalize_workspace_path(path, error_message="intended output must be a reviewable workspace artifact") for path in paths)
        for path in normalized:
            _ensure_reviewable_workspace_artifact(path, field_name="intended output")
        return normalized

    @model_validator(mode="after")
    def _validate_route_and_candidate_kind(self) -> FigureArtifactManifest:
        _validate_figure_route(
            figure_type=self.figure_type,
            strategy=self.strategy,
            evidence_level=self.evidence_level,
        )
        expected_kind = {
            "generative": "transient_preview",
            "code": "sandbox_artifact",
            "structured": "sandbox_artifact",
        }[_render_kind_for_strategy(self.strategy)]
        if self.candidate.kind != expected_kind:
            raise ValueError(f"strategy {self.strategy} requires {expected_kind} candidate ref")
        return self


def _render_kind_for_strategy(strategy: FigureStrategy) -> Literal["code", "structured", "generative"]:
    if strategy in CHART_CODE_STRATEGIES or strategy == "python_schematic":
        return "code"
    if strategy in STRUCTURED_STRATEGIES:
        return "structured"
    if strategy in AI_IMAGE_STRATEGIES:
        return "generative"
    raise ValueError(f"unsupported figure strategy: {strategy}")


def _normalize_workspace_path(path: str, *, error_message: str) -> str:
    try:
        return normalize_workspace_virtual_path(path)
    except ValueError as exc:
        raise ValueError(error_message) from exc


def _ensure_safe_workspace_path(path: str) -> str:
    normalized = _normalize_workspace_path(path, error_message="unsafe workspace path")
    if ".wenjin" in normalized.split("/"):
        raise ValueError("unsafe workspace path")
    if is_workspace_protected_path(normalized) or is_workspace_internal_path(normalized):
        raise ValueError("unsafe workspace path")
    return normalized


def _ensure_reviewable_workspace_artifact(path: str, *, field_name: str) -> None:
    if ".wenjin" in path.split("/") or not is_user_reviewable_workspace_artifact_path(path):
        raise ValueError(f"{field_name} must be a reviewable workspace artifact")
