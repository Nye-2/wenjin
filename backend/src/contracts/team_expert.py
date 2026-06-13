"""Contracts for user-visible Workbench expert-team presentation."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ExpertStatus = Literal["queued", "running", "blocked", "completed", "failed"]
ExpertUpdateKind = Literal["progress", "finding", "risk", "decision", "output", "question"]
ExpertTone = Literal["professional", "witty_professional"]
SnapshotTone = Literal["neutral", "info", "success", "warning", "danger"]
ExpertRefType = Literal["paper", "source", "file", "dataset", "artifact", "sandbox"]
ExpertOutputKind = Literal[
    "report",
    "matrix",
    "document",
    "file_change",
    "artifact",
    "literature_list",
    "claim_set",
    "experiment_summary",
]
PreviewStatus = Literal["draft", "ready", "saved"]

_STATUS_KEYS = {"queued", "running", "blocked", "completed", "failed"}
_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|authorization|credential|password)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{6,}\b"),
)
_HOST_PATH_RE = re.compile(r"(?<!\S)/(Users|private|var|tmp)/[^\s,;]+")
_MAX_HEADLINE_CHARS = 160
_MAX_BODY_CHARS = 500
_MAX_TITLE_CHARS = 120
_MAX_SUMMARY_CHARS = 500


class ExpertProfileV1(BaseModel):
    """Public identity for an agent template."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wenjin.team.expert_profile.v1"] = "wenjin.team.expert_profile.v1"
    public_name: str = Field(min_length=1, max_length=40)
    short_name: str | None = Field(default=None, max_length=16)
    role_title: str = Field(min_length=1, max_length=40)
    avatar_label: str | None = Field(default=None, max_length=3)
    tone: ExpertTone = "professional"
    tagline: str | None = Field(default=None, max_length=80)
    status_phrases: dict[str, str] = Field(default_factory=dict)
    preview_preferences: dict[str, Any] = Field(default_factory=dict)

    @field_validator("public_name", "short_name", "role_title", "avatar_label", "tagline")
    @classmethod
    def _clean_text_field(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("status_phrases")
    @classmethod
    def _validate_status_phrases(cls, value: dict[str, str]) -> dict[str, str]:
        result: dict[str, str] = {}
        invalid: list[str] = []
        for key, phrase in value.items():
            clean_key = str(key or "").strip()
            if clean_key not in _STATUS_KEYS:
                invalid.append(clean_key)
                continue
            clean_phrase = _clean_text(phrase)[:60]
            if clean_phrase:
                result[clean_key] = clean_phrase
        if invalid:
            raise ValueError(f"status_phrases has unknown status keys: {', '.join(invalid)}")
        return result

    @field_validator("preview_preferences")
    @classmethod
    def _bound_preview_preferences(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        result = dict(value)
        raw_kinds = result.get("primary_kinds")
        if isinstance(raw_kinds, list | tuple | set):
            result["primary_kinds"] = _unique_strings(raw_kinds)[:8]
        elif raw_kinds is not None:
            result.pop("primary_kinds", None)
        return result


class ExpertProfileOverrideV1(BaseModel):
    """Capability-local display override for an expert profile."""

    model_config = ConfigDict(extra="forbid")

    public_name: str | None = Field(default=None, min_length=1, max_length=40)
    short_name: str | None = Field(default=None, max_length=16)
    role_title: str | None = Field(default=None, min_length=1, max_length=40)
    avatar_label: str | None = Field(default=None, max_length=3)
    tone: ExpertTone | None = None
    tagline: str | None = Field(default=None, max_length=80)
    status_phrases: dict[str, str] = Field(default_factory=dict)
    preview_preferences: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status_phrases")
    @classmethod
    def _validate_status_phrases(cls, value: dict[str, str]) -> dict[str, str]:
        return ExpertProfileV1(
            public_name="placeholder",
            role_title="placeholder",
            status_phrases=value,
        ).status_phrases


class CapabilityTeamPresentationV1(BaseModel):
    """Capability extension for expert-team display customization."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wenjin.team.presentation.v1"] = "wenjin.team.presentation.v1"
    leader_virtual_member: ExpertProfileOverrideV1 | None = None
    template_overrides: dict[str, ExpertProfileOverrideV1] = Field(default_factory=dict)


class ExpertSnapshotStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    order: int | None = None


class ExpertSnapshotChip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: str | None = None
    tone: SnapshotTone | None = None


class ExpertSnapshotRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    ref_type: ExpertRefType
    ref_id: str | None = None
    path: str | None = None
    count: int | None = None


class ExpertSnapshotOutputRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    kind: ExpertOutputKind
    ref_id: str | None = None
    preview_item_id: str | None = None
    path: str | None = None
    status: Literal["draft", "ready", "staged", "applied"] | None = None


class ExpertThoughtSnapshotV1(BaseModel):
    """Bounded user-visible progress/finding snapshot emitted by an expert."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wenjin.team.expert_snapshot.v1"] = "wenjin.team.expert_snapshot.v1"
    snapshot_id: str
    execution_id: str
    workspace_id: str
    node_id: str | None = None
    agent_invocation_id: str
    agent_template_id: str
    role_key: str
    role_name: str
    display_name: str | None = None
    status: ExpertStatus
    update_kind: ExpertUpdateKind
    stage: ExpertSnapshotStage
    headline: str
    body: str
    chips: list[ExpertSnapshotChip] = Field(default_factory=list)
    evidence_refs: list[ExpertSnapshotRef] = Field(default_factory=list)
    output_refs: list[ExpertSnapshotOutputRef] = Field(default_factory=list)
    next_step: str | None = None
    confidence: Literal["low", "medium", "high"] | None = None
    created_at: str
    replaces_snapshot_id: str | None = None


class ExpertPreviewItemV1(BaseModel):
    """Bounded user-visible preview item owned by an expert invocation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wenjin.team.expert_preview_item.v1"] = "wenjin.team.expert_preview_item.v1"
    preview_item_id: str
    execution_id: str
    workspace_id: str
    owner_agent_invocation_id: str
    owner_role_name: str
    title: str
    subtitle: str | None = None
    kind: ExpertOutputKind
    summary: str
    preview_payload_ref: str | None = None
    source_snapshot_id: str | None = None
    source_refs: list[ExpertSnapshotRef] = Field(default_factory=list)
    status: PreviewStatus
    created_at: str


def resolve_expert_profile(
    *,
    base_profile: ExpertProfileV1 | dict[str, Any] | None,
    display_role: str,
    override: ExpertProfileOverrideV1 | dict[str, Any] | None = None,
) -> ExpertProfileV1:
    """Resolve template profile plus capability display override."""

    if isinstance(base_profile, ExpertProfileV1):
        data = base_profile.model_dump(mode="json")
    elif isinstance(base_profile, dict):
        data = ExpertProfileV1.model_validate(base_profile).model_dump(mode="json")
    else:
        role = _clean_text(display_role) or "专家"
        data = {
            "public_name": role,
            "role_title": role,
            "avatar_label": role[:1] or "专",
            "tone": "professional",
        }

    if override:
        override_model = (
            override
            if isinstance(override, ExpertProfileOverrideV1)
            else ExpertProfileOverrideV1.model_validate(override)
        )
        override_data = override_model.model_dump(exclude_none=True, mode="json")
        merged_status = {
            **dict(data.get("status_phrases") or {}),
            **dict(override_data.pop("status_phrases", {}) or {}),
        }
        merged_preview_preferences = {
            **dict(data.get("preview_preferences") or {}),
            **dict(override_data.pop("preview_preferences", {}) or {}),
        }
        data.update(override_data)
        if merged_status:
            data["status_phrases"] = merged_status
        if merged_preview_preferences:
            data["preview_preferences"] = merged_preview_preferences

    if not data.get("avatar_label"):
        data["avatar_label"] = str(data.get("public_name") or "专")[:1]
    return ExpertProfileV1.model_validate(data)


def sanitize_expert_snapshot(payload: dict[str, Any]) -> ExpertThoughtSnapshotV1:
    """Validate and bound a raw expert snapshot for persistence/UI projection."""

    clean_refs = _sanitize_refs(payload.get("evidence_refs"), limit=5)
    clean_output_refs = _sanitize_output_refs(payload.get("output_refs"), limit=3)
    raw_stage = payload.get("stage")
    stage = raw_stage if isinstance(raw_stage, dict) else {}
    data = {
        "schema_version": "wenjin.team.expert_snapshot.v1",
        "snapshot_id": _clean_text(payload.get("snapshot_id")),
        "execution_id": _clean_text(payload.get("execution_id")),
        "workspace_id": _clean_text(payload.get("workspace_id")),
        "node_id": _optional_clean_text(payload.get("node_id")),
        "agent_invocation_id": _clean_text(payload.get("agent_invocation_id")),
        "agent_template_id": _clean_text(payload.get("agent_template_id")),
        "role_key": _clean_text(payload.get("role_key")),
        "role_name": _clean_text(payload.get("role_name")),
        "display_name": _optional_clean_text(payload.get("display_name")),
        "status": payload.get("status"),
        "update_kind": payload.get("update_kind"),
        "stage": {
            "label": _truncate(_clean_text(stage.get("label")), 40),
            "order": stage.get("order"),
        },
        "headline": _truncate(_scrub_text(payload.get("headline")), _MAX_HEADLINE_CHARS),
        "body": _truncate(_scrub_text(payload.get("body")), _MAX_BODY_CHARS),
        "chips": _sanitize_chips(payload.get("chips"), limit=5),
        "evidence_refs": clean_refs,
        "output_refs": clean_output_refs,
        "next_step": _optional_truncated_scrubbed(payload.get("next_step"), 160),
        "confidence": payload.get("confidence"),
        "created_at": _clean_text(payload.get("created_at")),
        "replaces_snapshot_id": _optional_clean_text(payload.get("replaces_snapshot_id")),
    }
    return ExpertThoughtSnapshotV1.model_validate(data)


def sanitize_expert_preview_item(payload: dict[str, Any]) -> ExpertPreviewItemV1:
    """Validate and bound a raw expert preview item for persistence/UI projection."""

    payload_ref = _optional_clean_text(payload.get("preview_payload_ref"))
    if payload_ref and not _is_safe_ref_path(payload_ref):
        payload_ref = None
    data = {
        "schema_version": "wenjin.team.expert_preview_item.v1",
        "preview_item_id": _clean_text(payload.get("preview_item_id")),
        "execution_id": _clean_text(payload.get("execution_id")),
        "workspace_id": _clean_text(payload.get("workspace_id")),
        "owner_agent_invocation_id": _clean_text(payload.get("owner_agent_invocation_id")),
        "owner_role_name": _clean_text(payload.get("owner_role_name")),
        "title": _truncate(_scrub_text(payload.get("title")), _MAX_TITLE_CHARS),
        "subtitle": _optional_truncated_scrubbed(payload.get("subtitle"), 120),
        "kind": payload.get("kind"),
        "summary": _truncate(_scrub_text(payload.get("summary")), _MAX_SUMMARY_CHARS),
        "preview_payload_ref": payload_ref,
        "source_snapshot_id": _optional_clean_text(payload.get("source_snapshot_id")),
        "source_refs": _sanitize_refs(payload.get("source_refs"), limit=8),
        "status": payload.get("status"),
        "created_at": _clean_text(payload.get("created_at")),
    }
    return ExpertPreviewItemV1.model_validate(data)


def _sanitize_chips(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    chips: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        label = _truncate(_scrub_text(item.get("label")), 24)
        if not label:
            continue
        chip = {
            "label": label,
            "value": _optional_truncated_scrubbed(item.get("value"), 40),
            "tone": item.get("tone"),
        }
        chips.append({key: val for key, val in chip.items() if val is not None})
        if len(chips) >= limit:
            break
    return chips


def _sanitize_refs(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    refs: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path = _optional_clean_text(item.get("path"))
        if path and not _is_safe_ref_path(path):
            continue
        label = _truncate(_scrub_text(item.get("label")), 80)
        ref_type = _clean_text(item.get("ref_type"))
        if not label or not ref_type:
            continue
        ref = {
            "label": label,
            "ref_type": ref_type,
            "ref_id": _optional_clean_text(item.get("ref_id")),
            "path": path,
            "count": item.get("count") if isinstance(item.get("count"), int) else None,
        }
        refs.append({key: val for key, val in ref.items() if val is not None})
        if len(refs) >= limit:
            break
    return refs


def _sanitize_output_refs(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    refs: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path = _optional_clean_text(item.get("path"))
        if path and not _is_safe_ref_path(path):
            continue
        label = _truncate(_scrub_text(item.get("label")), 80)
        kind = _clean_text(item.get("kind"))
        if not label or not kind:
            continue
        ref = {
            "label": label,
            "kind": kind,
            "ref_id": _optional_clean_text(item.get("ref_id")),
            "preview_item_id": _optional_clean_text(item.get("preview_item_id")),
            "path": path,
            "status": item.get("status"),
        }
        refs.append({key: val for key, val in ref.items() if val is not None})
        if len(refs) >= limit:
            break
    return refs


def _is_safe_ref_path(path: str) -> bool:
    text = _clean_text(path)
    if not text:
        return False
    if "/.harness/" in text or text.startswith("/workspace/tmp/tasks/"):
        return False
    if text.startswith("/workspace/"):
        return True
    if text.startswith("workspace/"):
        return True
    if text.startswith("sandbox://") or text.startswith("workspace://"):
        return True
    if text.startswith("/"):
        return False
    return "/" not in text or text.startswith("outputs/")


def _optional_truncated_scrubbed(value: Any, limit: int) -> str | None:
    text = _truncate(_scrub_text(value), limit)
    return text or None


def _scrub_text(value: Any) -> str:
    text = _clean_text(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    text = _HOST_PATH_RE.sub("[local-path]", text)
    return text


def _truncate(value: str, limit: int) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    return text[:limit]


def _optional_clean_text(value: Any) -> str | None:
    text = _clean_text(value)
    return text or None


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _clean_text(item)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result
