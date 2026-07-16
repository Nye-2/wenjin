"""Content-addressed inputs pinned to a durable Mission."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MISSION_INPUT_REF_PATTERN = r"^mission-input:[0-9a-f]{64}$"
MAX_MISSION_INPUTS = 32


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MissionInputManifest(_FrozenContract):
    """Immutable extracted text plus the uploaded source identity that produced it."""

    schema_version: Literal["1"] = "1"
    input_ref: str = Field(pattern=MISSION_INPUT_REF_PATTERN)
    workspace_id: str = Field(min_length=1, max_length=160)
    thread_id: str = Field(min_length=1, max_length=160)
    filename: str = Field(min_length=1, max_length=500)
    mime_type: str | None = Field(default=None, max_length=200)
    extractor: Literal["preprocessed_markdown", "pdf_text", "plain_text"]
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_size_bytes: int = Field(ge=1, le=100 * 1024 * 1024)
    text_size_bytes: int = Field(ge=1, le=8 * 1024 * 1024)
    text_chars: int = Field(ge=1, le=8 * 1024 * 1024)

    @model_validator(mode="after")
    def bind_reference_to_content_hash(self) -> MissionInputManifest:
        digest = self.input_ref.removeprefix("mission-input:")
        if self.content_hash != f"sha256:{digest}":
            raise ValueError("mission input ref must equal the extracted content hash")
        return self


class MissionInputContext(_FrozenContract):
    """Bounded, model-safe projection of one uploaded file."""

    name: str = Field(min_length=1, max_length=500)
    content_type: str | None = Field(default=None, max_length=200)
    size_bytes: int | None = Field(default=None, ge=0, le=100 * 1024 * 1024)
    status: Literal["ready", "pending", "unreadable"]
    input_ref: str | None = Field(default=None, pattern=MISSION_INPUT_REF_PATTERN)
    excerpt: str | None = Field(default=None, max_length=12_000)
    detail: str | None = Field(default=None, max_length=500)
    current_message: bool = False

    @model_validator(mode="after")
    def ready_context_requires_ref(self) -> MissionInputContext:
        if self.status == "ready" and not self.input_ref:
            raise ValueError("ready mission input context requires input_ref")
        if self.status != "ready" and self.input_ref:
            raise ValueError("unavailable mission input context cannot expose input_ref")
        return self


def validate_mission_input_manifests(
    values: list[dict[str, Any]] | tuple[dict[str, Any], ...] | tuple[MissionInputManifest, ...],
    *,
    workspace_id: str,
    thread_id: str | None = None,
) -> tuple[MissionInputManifest, ...]:
    """Validate, workspace-bind, and de-duplicate a bounded manifest sequence."""

    manifests: list[MissionInputManifest] = []
    seen: set[str] = set()
    for value in values:
        manifest = value if isinstance(value, MissionInputManifest) else MissionInputManifest.model_validate(value)
        if manifest.workspace_id != workspace_id:
            raise ValueError("mission input belongs to another workspace")
        if thread_id is not None and manifest.thread_id != thread_id:
            raise ValueError("mission input belongs to another conversation thread")
        if manifest.input_ref in seen:
            continue
        seen.add(manifest.input_ref)
        manifests.append(manifest)
        if len(manifests) > MAX_MISSION_INPUTS:
            raise ValueError(f"a Mission may pin at most {MAX_MISSION_INPUTS} inputs")
    return tuple(manifests)


def merge_mission_input_manifests(
    existing: object,
    incoming: object,
    *,
    workspace_id: str,
    thread_id: str | None = None,
) -> list[dict[str, Any]]:
    """Merge new manifests into the Mission snapshot without aliases or duplicate refs."""

    prior = existing if isinstance(existing, list) else []
    additions = incoming if isinstance(incoming, list) else []
    merged = validate_mission_input_manifests(
        tuple(item for item in [*prior, *additions] if isinstance(item, dict)),
        workspace_id=workspace_id,
        thread_id=thread_id,
    )
    return [item.model_dump(mode="json") for item in merged]


__all__ = [
    "MAX_MISSION_INPUTS",
    "MISSION_INPUT_REF_PATTERN",
    "MissionInputContext",
    "MissionInputManifest",
    "merge_mission_input_manifests",
    "validate_mission_input_manifests",
]
