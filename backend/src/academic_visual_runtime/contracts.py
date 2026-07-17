"""Runtime-only contracts layered on the canonical figure-generation SSOT."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.contracts.figure_generation import (
    AcademicFigureBrief,
    AcademicVisualCandidate,
    AcademicVisualRenderInput,
    CodeVisualPayload,
    ExactVisualLabel,
    FigureArtifactManifest,
    GenerativeVisualPayload,
    StructuredVisualPayload,
    VisualCandidateRef,
    VisualContentHash,
)


class AcademicVisualExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=160)
    mission_id: str = Field(min_length=1, max_length=160)
    caller_id: str = Field(min_length=1, max_length=160)
    caller_kind: Literal["workspace_agent", "subagent"]
    lease_epoch: int = Field(ge=0)
    policy_version: str = Field(min_length=1, max_length=300)
    prism_context_text: str | None = Field(default=None, max_length=16_000)
    prism_context_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_prism_context_pair(self) -> AcademicVisualExecutionContext:
        if (self.prism_context_text is None) != (self.prism_context_hash is None):
            raise ValueError("resolved Prism context text and hash must be supplied together")
        return self


class AcademicVisualReceipt(BaseModel):
    """One strategy-neutral receipt consumed by the canonical Mission tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_: Literal["wenjin.academic_visual.receipt.v1"] = Field(
        default="wenjin.academic_visual.receipt.v1",
        alias="schema",
    )
    candidate: AcademicVisualCandidate
    manifest: FigureArtifactManifest


class AcademicVisualOperationIdentity(BaseModel):
    """Server-built semantic identity projected before any visual side effect."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_: Literal["wenjin.academic_visual.operation_identity.v1"] = Field(
        default="wenjin.academic_visual.operation_identity.v1",
        alias="schema",
    )
    source_item_seq: int = Field(ge=1)
    variant_ordinal: int = Field(default=0, ge=0)
    figure_id: str = Field(min_length=1, max_length=120)
    brief_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    render_contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_hashes: tuple[str, ...] = ()
    renderer_id: str = Field(min_length=1, max_length=120)
    renderer_version: str = Field(min_length=1, max_length=120)
    source_semantic_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_contract_version: str | None = Field(default=None, max_length=120)
    prompt_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    dataset_content_hashes: dict[str, VisualContentHash] = Field(default_factory=dict)
    source_content_hashes: dict[str, VisualContentHash] = Field(default_factory=dict)
    provider_model: Literal["gpt-image-2"] | None = None
    quality: Literal["low", "medium", "high", "auto"] | None = None
    size: Literal["1024x1024", "1536x1024", "1024x1536"] | None = None
    overlay_manifest_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


__all__ = [
    "AcademicFigureBrief",
    "AcademicVisualCandidate",
    "AcademicVisualExecutionContext",
    "AcademicVisualOperationIdentity",
    "AcademicVisualReceipt",
    "AcademicVisualRenderInput",
    "CodeVisualPayload",
    "ExactVisualLabel",
    "FigureArtifactManifest",
    "GenerativeVisualPayload",
    "StructuredVisualPayload",
    "VisualCandidateRef",
]
