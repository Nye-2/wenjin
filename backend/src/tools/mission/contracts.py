"""Strict model-facing inputs for canonical Mission tools."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from src.academic_visual_runtime.contracts import AcademicVisualRenderInput


class MissionToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ListWorkspaceAssetsInput(MissionToolInput):
    asset_kind: str | None = Field(default=None, max_length=80)
    limit: int = Field(default=30, ge=1, le=100)


class ReadWorkspaceAssetInput(MissionToolInput):
    asset_ref: str = Field(pattern=r"^asset:[A-Za-z0-9-]+$", max_length=166)
    offset: int = Field(default=0, ge=0)
    max_bytes: int = Field(default=24_000, ge=1, le=65_536)


class ReadMissionInputInput(MissionToolInput):
    input_ref: str = Field(pattern=r"^mission-input:[0-9a-f]{64}$")
    offset: int = Field(default=0, ge=0, le=8 * 1024 * 1024)
    max_chars: int = Field(default=24_000, ge=1, le=65_536)


class ListWorkspaceDocumentsInput(MissionToolInput):
    limit: int = Field(default=50, ge=1, le=100)


class ReadWorkspaceDocumentInput(MissionToolInput):
    document_ref: str = Field(pattern=r"^prism-file:[A-Za-z0-9-]+$", max_length=171)
    offset: int = Field(default=0, ge=0)
    max_chars: int = Field(default=24_000, ge=1, le=65_536)


class SearchWorkspaceSourceTextInput(MissionToolInput):
    query: str = Field(min_length=1, max_length=1_000)
    source_ids: tuple[str, ...] = Field(default=(), max_length=50)
    limit: int = Field(default=8, ge=1, le=20)


class ImportSourceCandidateInput(MissionToolInput):
    title: str = Field(min_length=1, max_length=500)
    citation_key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_:-]{0,119}$")
    verification_ref: str = Field(min_length=1, max_length=1_000)
    source_kind: Literal["paper", "web_page", "dataset", "manual"] = "paper"
    authors: tuple[str, ...] = Field(default=(), max_length=100)
    year: int | None = Field(default=None, ge=1000, le=2200)
    venue: str | None = Field(default=None, max_length=300)
    doi: str | None = Field(default=None, max_length=300)
    url: str | None = Field(default=None, max_length=2_048)
    abstract: str | None = Field(default=None, max_length=20_000)

    @model_validator(mode="after")
    def require_verifiable_origin(self) -> ImportSourceCandidateInput:
        if not (self.verification_ref.startswith("asset:") or self.verification_ref.startswith("source:") or self.verification_ref.startswith("search-receipt:")):
            raise ValueError("verification_ref must name a workspace asset, existing source, or Mission search receipt")
        if self.verification_ref.startswith("search-receipt:") and not self.url:
            raise ValueError("search receipt imports require url")
        return self


class ListSourceCodeFilesInput(MissionToolInput):
    asset_ref: str = Field(pattern=r"^asset:[A-Za-z0-9-]+$", max_length=166)
    relative_dir: str = Field(default=".", min_length=1, max_length=500)
    limit: int = Field(default=200, ge=1, le=500)


class ReadSourceCodeFileInput(MissionToolInput):
    asset_ref: str = Field(pattern=r"^asset:[A-Za-z0-9-]+$", max_length=166)
    relative_path: str = Field(min_length=1, max_length=500)
    offset: int = Field(default=0, ge=0)
    max_bytes: int = Field(default=32_000, ge=1, le=131_072)


class RunPythonToolInput(MissionToolInput):
    script: str = Field(
        min_length=1,
        max_length=2_000_000,
        description=("Complete replacement contents for script_path. The Sandbox writes this value to script_path before execution; never submit a patcher that reads or rewrites script_path."),
    )
    script_path: str = Field(
        default="/workspace/scripts/analysis.py",
        min_length=1,
        max_length=500,
        description="Stable path that will be atomically replaced with the complete script, then executed.",
    )
    environment_id: str | None = Field(default=None, max_length=100)
    dataset_paths: tuple[str, ...] = Field(default=(), max_length=100)


class RunNotebookToolInput(MissionToolInput):
    notebook_path: str = Field(min_length=1, max_length=500)
    output_path: str = Field(min_length=1, max_length=500)
    environment_id: str = Field(min_length=1, max_length=100)
    dataset_paths: tuple[str, ...] = Field(default=(), max_length=100)


class SmokeCheckToolInput(MissionToolInput):
    pass


class InstallDependenciesToolInput(MissionToolInput):
    packages: tuple[str, ...] = Field(min_length=1, max_length=100)
    permission_request_id: str = Field(min_length=1, max_length=100)
    permission_expires_at: datetime


class RegisterDatasetToolInput(MissionToolInput):
    path: str = Field(min_length=1, max_length=500)
    source: str = Field(min_length=1, max_length=1_000)
    license: str | None = Field(default=None, max_length=200)
    pii_risk: Literal["none", "possible", "confirmed", "unknown"] = "unknown"
    observed_at: datetime


class RegisterArtifactToolInput(MissionToolInput):
    path: str = Field(
        min_length=1,
        max_length=500,
        description="Reviewable artifact path under /workspace/outputs or /workspace/reports; task scratch is temporary and cannot be registered.",
    )
    producing_operation_key: str = Field(pattern=r"^sbxop_[0-9a-f]{64}$")


class ReadSandboxOutputInput(MissionToolInput):
    output_ref: str = Field(pattern=r"^sbxout_[A-Za-z0-9_-]{20,}$")
    offset: int = Field(default=0, ge=0)
    max_bytes: int = Field(default=32_768, ge=1, le=131_072)


class ReadSandboxArtifactInput(MissionToolInput):
    artifact_ref: str = Field(pattern=r"^sandbox-artifact:[0-9a-f]{64}$")
    offset: int = Field(default=0, ge=0, le=16_777_216)
    max_bytes: int = Field(default=24_000, ge=1_024, le=32_000)


class ReadSandboxFileInput(MissionToolInput):
    path: str = Field(
        pattern=r"^/workspace/(?:scripts|outputs|reports)/[^\x00]+$",
        max_length=500,
    )
    max_bytes: int = Field(default=65_536, ge=1, le=131_072)


class CreateArtifactCandidateInput(MissionToolInput):
    title: str = Field(min_length=1, max_length=200)
    artifact_kind: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[a-z][a-z0-9_.:-]*$",
        description="Semantic output kind required by the current StageAcceptanceContract.",
    )
    source_refs: tuple[str, ...] = Field(
        default=(),
        max_length=100,
        description=(
            "Exact canonical provenance refs only: asset:, prism-file:, source:, "
            "artifact-candidate:<sha256>, academic-visual:<id>, "
            "sandbox-artifact:<sha256>, or mission-input:<sha256>. A sandbox-file: "
            "read receipt is not a durable artifact ref."
        ),
    )
    mime_type: Literal["text/markdown"] = "text/markdown"
    preview_text: str = Field(min_length=1, max_length=160_000)
    metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict,
        description=(
            "Optional flat scalar metadata. Put lists, tables, nested structures, "
            "and the complete deliverable in preview_text."
        ),
    )

    @field_validator("source_refs")
    @classmethod
    def validate_source_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise PydanticCustomError(
                "duplicate_reference",
                "source refs must be unique",
            )
        canonical_ref = re.compile(
            r"^(?:(?:asset|prism-file|source):[A-Za-z0-9][A-Za-z0-9._:-]{0,2047}"
            r"|(?:artifact-candidate|sandbox-artifact|mission-input):[0-9a-f]{64}"
            r"|academic-visual:[A-Za-z0-9][A-Za-z0-9._:-]{0,159})$"
        )
        if any(canonical_ref.fullmatch(ref) is None for ref in value):
            raise PydanticCustomError(
                "invalid_canonical_reference",
                "source refs must use canonical reference syntax",
            )
        return value


class ReadArtifactCandidateInput(MissionToolInput):
    candidate_ref: str = Field(
        pattern=(
            r"^(?:artifact-candidate:[0-9a-f]{64}"
            r"|academic-visual:[A-Za-z0-9][A-Za-z0-9._:-]{0,159})$"
        )
    )


MISSION_TOOL_INPUT_MODELS: dict[str, type[BaseModel]] = {
    "workspace.list_assets": ListWorkspaceAssetsInput,
    "workspace.read_asset": ReadWorkspaceAssetInput,
    "workspace.read_input": ReadMissionInputInput,
    "workspace.list_documents": ListWorkspaceDocumentsInput,
    "workspace.read_document": ReadWorkspaceDocumentInput,
    "workspace.search_source_text": SearchWorkspaceSourceTextInput,
    "artifact.read_candidate": ReadArtifactCandidateInput,
    "source.import_candidate": ImportSourceCandidateInput,
    "source_code.list_files": ListSourceCodeFilesInput,
    "source_code.read_file": ReadSourceCodeFileInput,
    "sandbox.run_python": RunPythonToolInput,
    "sandbox.run_notebook": RunNotebookToolInput,
    "sandbox.smoke_check": SmokeCheckToolInput,
    "sandbox.install_dependencies": InstallDependenciesToolInput,
    "sandbox.register_dataset": RegisterDatasetToolInput,
    "sandbox.register_artifact": RegisterArtifactToolInput,
    "sandbox.read_artifact": ReadSandboxArtifactInput,
    "sandbox.read_file": ReadSandboxFileInput,
    "sandbox.read_output_ref": ReadSandboxOutputInput,
    "artifact.create_candidate": CreateArtifactCandidateInput,
    "academic_visual.render_candidate": AcademicVisualRenderInput,
}


__all__ = [name for name in globals() if name.endswith("Input")] + [
    "MISSION_TOOL_INPUT_MODELS",
]
