"""Contracts for research figure generation specs and artifacts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    "graphical_abstract",
    "patent_drawing",
    "table_visual",
    "ui_screenshot",
    "geometric_schematic",
    "simulation_snapshot",
    "other",
]

FigureStrategy = Literal[
    "matplotlib",
    "seaborn",
    "plotly_static",
    "mermaid",
    "graphviz",
    "tikz",
    "llm_image",
    "hybrid",
    "playwright_screenshot",
    "python_schematic",
    "uploaded_artifact",
]

EvidenceLevel = Literal["evidence", "explanatory", "decorative"]

CHART_CODE_STRATEGIES = frozenset({"matplotlib", "seaborn", "plotly_static"})
CODE_REQUIRED_TYPES = frozenset({"data_plot", "experiment_plot", "statistical_chart", "table_visual"})
STRUCTURED_REQUIRED_TYPES = frozenset({"architecture_diagram", "method_flow", "patent_drawing"})
STRUCTURED_STRATEGIES = frozenset({"mermaid", "graphviz", "tikz"})
SCREENSHOT_TYPES = frozenset({"ui_screenshot"})
SCREENSHOT_STRATEGIES = frozenset({"playwright_screenshot"})
SOURCE_ARTIFACT_STRATEGIES = frozenset({"uploaded_artifact"})
AI_IMAGE_STRATEGIES = frozenset({"llm_image", "hybrid"})


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
    inputs: dict[str, Any] = Field(default_factory=dict)
    output_targets: list[str] = Field(default_factory=list)
    caption: str | None = None
    alt_text: str | None = None
    dataset_paths: list[str] = Field(default_factory=list)
    source_artifact_paths: list[str] = Field(default_factory=list)
    reproducibility_command: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    quality_checks: list[str] = Field(default_factory=list)

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

    @field_validator("source_artifact_paths")
    @classmethod
    def _validate_source_artifact_paths(cls, paths: list[str]) -> list[str]:
        return [_ensure_safe_workspace_path(path) for path in paths]

    @model_validator(mode="after")
    def _validate_strategy_and_targets(self) -> FigureSpec:
        if self.evidence_level == "evidence" and self.strategy in AI_IMAGE_STRATEGIES:
            raise ValueError("evidence figures cannot use AI image generation strategies")
        if self.figure_type in CODE_REQUIRED_TYPES and self.strategy not in CHART_CODE_STRATEGIES:
            if self.strategy in {"llm_image", "hybrid"}:
                raise ValueError("data figures must use code generation strategies")
            raise ValueError("data figures must use chart code generation strategies")
        if self.figure_type in STRUCTURED_REQUIRED_TYPES and self.strategy not in STRUCTURED_STRATEGIES:
            raise ValueError("structured figures must use structured diagram strategies")
        if self.figure_type in SCREENSHOT_TYPES:
            if self.strategy in AI_IMAGE_STRATEGIES:
                raise ValueError("ui screenshots require playwright_screenshot or uploaded_artifact source_artifact_paths")
            if self.strategy in SCREENSHOT_STRATEGIES:
                pass
            elif self.strategy in SOURCE_ARTIFACT_STRATEGIES and self.source_artifact_paths:
                pass
            else:
                raise ValueError(
                    "ui screenshots require playwright_screenshot or uploaded_artifact source_artifact_paths"
                )
        for path in self.output_targets:
            _ensure_reviewable_workspace_artifact(path, field_name="output target")
        return self


class FigureArtifactManifest(BaseModel):
    """Manifest for a generated figure artifact staged for review."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["wenjin.figure_generation.artifact.v1"] = Field(
        default="wenjin.figure_generation.artifact.v1",
        alias="schema",
    )
    figure_id: str = Field(min_length=1, max_length=120)
    figure_type: FigureType
    strategy: FigureStrategy
    primary_path: str
    source_script: str | None = None
    source_prompt: str | None = None
    dataset_paths: list[str] = Field(default_factory=list)
    caption_path: str | None = None
    alt_text_path: str | None = None
    created_by: str | None = None
    content_hash: str | None = None
    review_notes: str | None = None

    @property
    def schema(self) -> str:
        return self.schema_

    @field_validator("primary_path")
    @classmethod
    def _validate_primary_path(cls, path: str) -> str:
        normalized = _normalize_workspace_path(path, error_message="primary_path must be a reviewable workspace artifact")
        _ensure_reviewable_workspace_artifact(normalized, field_name="primary_path")
        return normalized

    @field_validator("source_script", "caption_path", "alt_text_path")
    @classmethod
    def _validate_optional_workspace_path(cls, path: str | None) -> str | None:
        if path is not None:
            return _ensure_safe_workspace_path(path)
        return None

    @field_validator("dataset_paths")
    @classmethod
    def _validate_dataset_paths(cls, paths: list[str]) -> list[str]:
        return [_ensure_safe_workspace_path(path) for path in paths]


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
