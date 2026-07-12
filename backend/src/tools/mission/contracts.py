"""Strict model-facing inputs for canonical Mission tools."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MissionToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ListWorkspaceAssetsInput(MissionToolInput):
    asset_kind: str | None = Field(default=None, max_length=80)
    limit: int = Field(default=30, ge=1, le=100)


class ReadWorkspaceAssetInput(MissionToolInput):
    asset_id: str = Field(min_length=1, max_length=160)
    offset: int = Field(default=0, ge=0)
    max_bytes: int = Field(default=24_000, ge=1, le=65_536)


class ListWorkspaceDocumentsInput(MissionToolInput):
    limit: int = Field(default=50, ge=1, le=100)


class ReadWorkspaceDocumentInput(MissionToolInput):
    file_id: str = Field(min_length=1, max_length=160)
    offset: int = Field(default=0, ge=0)
    max_chars: int = Field(default=24_000, ge=1, le=65_536)


class ReadMissionReviewCandidateInput(MissionToolInput):
    review_item_id: str = Field(min_length=1, max_length=160)


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
    asset_id: str = Field(min_length=1, max_length=160)
    relative_dir: str = Field(default=".", min_length=1, max_length=500)
    limit: int = Field(default=200, ge=1, le=500)


class ReadSourceCodeFileInput(MissionToolInput):
    asset_id: str = Field(min_length=1, max_length=160)
    relative_path: str = Field(min_length=1, max_length=500)
    offset: int = Field(default=0, ge=0)
    max_bytes: int = Field(default=32_000, ge=1, le=131_072)


class RunPythonToolInput(MissionToolInput):
    script: str = Field(min_length=1, max_length=2_000_000)
    script_path: str = Field(default="/workspace/scripts/analysis.py", min_length=1, max_length=500)
    environment_id: str | None = Field(default=None, max_length=100)
    dataset_paths: tuple[str, ...] = Field(default=(), max_length=100)
    output_base_hashes: dict[str, str] = Field(default_factory=dict)


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
    path: str = Field(min_length=1, max_length=500)
    producing_operation_key: str = Field(pattern=r"^sbxop_[0-9a-f]{64}$")


class ReadSandboxOutputInput(MissionToolInput):
    output_ref: str = Field(pattern=r"^sbxout_[A-Za-z0-9_-]{20,}$")
    offset: int = Field(default=0, ge=0)
    max_bytes: int = Field(default=32_768, ge=1, le=131_072)


class CreateArtifactCandidateInput(MissionToolInput):
    title: str = Field(min_length=1, max_length=200)
    artifact_kind: Literal["document", "chart", "table", "figure", "report", "manifest"]
    source_refs: tuple[str, ...] = Field(min_length=1, max_length=100)
    mime_type: str = Field(min_length=1, max_length=120)
    preview_text: str | None = Field(default=None, max_length=24_000)
    sandbox_artifact_path: str | None = Field(default=None, max_length=500)
    content_hash: str | None = Field(default=None, pattern=r"^(?:sha256:)?[0-9a-f]{64}$")
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_previewable_payload(self) -> CreateArtifactCandidateInput:
        if not self.preview_text and not self.sandbox_artifact_path:
            raise ValueError("artifact candidate requires preview_text or sandbox_artifact_path")
        return self


__all__ = [name for name in globals() if name.endswith("Input")]
