"""Contracts for user-visible Workbench expert-team presentation."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.agents.harness.claim_evidence import (
    ClaimInventoryV1,
    EvidencePacketV1,
    sanitize_claim_inventory,
    sanitize_evidence_packet,
)
from src.agents.harness.research_brief import ResearchBriefDeltaV1, sanitize_research_brief_delta

ExpertStatus = Literal["queued", "running", "blocked", "completed", "failed"]
ExpertUpdateKind = Literal["progress", "finding", "risk", "decision", "output", "question"]
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
ExpertClaimSupportLevel = Literal["verified", "supported", "plausible", "weak", "unsupported"]
ExpertEvidenceSourceType = Literal[
    "library_reference",
    "document",
    "memory",
    "sandbox_artifact",
    "dataset",
    "prism",
    "expert_output",
]

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|authorization|credential|password)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{6,}\b"),
)
_HOST_PATH_RE = re.compile(r"(?<!\S)/(Users|private|var|tmp)/[^\s,;]+")
_MAX_HEADLINE_CHARS = 160
_MAX_BODY_CHARS = 500
_MAX_TITLE_CHARS = 120
_MAX_SUMMARY_CHARS = 500
_MAX_REPORT_SUMMARY_CHARS = 700
_MAX_CLAIM_TEXT_CHARS = 500
_MAX_EVIDENCE_EXCERPT_CHARS = 500


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


class ExpertClaimV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    text: str
    support_level: ExpertClaimSupportLevel
    evidence_ids: list[str] = Field(default_factory=list)
    citation_keys: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ExpertEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_type: ExpertEvidenceSourceType
    source_id: str | None = None
    citation_key: str | None = None
    relevance: Literal["low", "medium", "high"] | None = None
    risk: Literal["low", "medium", "high", "critical"] | None = None
    bounded_excerpt: str | None = None
    used_for: list[str] = Field(default_factory=list)


class ExpertArtifactV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    kind: str
    path: str
    source_script: str | None = None
    dataset_paths: list[str] = Field(default_factory=list)
    content_hash: str | None = None
    caption: str | None = None
    reviewable: bool = True


class ExpertReportV1(BaseModel):
    """Common structured output envelope for academic expert work."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wenjin.expert_report.v1"] = "wenjin.expert_report.v1"
    expert_id: str
    skill_id: str
    task_focus: str
    summary: str
    research_brief_delta: ResearchBriefDeltaV1 | None = None
    claims: list[ExpertClaimV1] = Field(default_factory=list)
    evidence: list[ExpertEvidenceV1] = Field(default_factory=list)
    claim_inventory: ClaimInventoryV1 | None = None
    evidence_packet: EvidencePacketV1 | None = None
    artifacts: list[ExpertArtifactV1] = Field(default_factory=list)
    review_items: list[dict[str, Any]] = Field(default_factory=list)
    quality_gates_checked: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    domain_payload: dict[str, Any] = Field(default_factory=dict)


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


def sanitize_expert_report(payload: dict[str, Any]) -> ExpertReportV1:
    """Validate and bound a raw expert report for review-packet mapping."""

    data = {
        "schema_version": "wenjin.expert_report.v1",
        "expert_id": _clean_text(payload.get("expert_id")),
        "skill_id": _clean_text(payload.get("skill_id")),
        "task_focus": _truncate(_scrub_text(payload.get("task_focus")), 300),
        "summary": _truncate(_scrub_text(payload.get("summary")), _MAX_REPORT_SUMMARY_CHARS),
        "research_brief_delta": sanitize_research_brief_delta(payload.get("research_brief_delta")),
        "claims": _sanitize_expert_claims(payload.get("claims"), limit=30),
        "evidence": _sanitize_expert_evidence(payload.get("evidence"), limit=60),
        "claim_inventory": sanitize_claim_inventory(payload.get("claim_inventory")),
        "evidence_packet": sanitize_evidence_packet(payload.get("evidence_packet")),
        "artifacts": _sanitize_expert_artifacts(payload.get("artifacts"), limit=20),
        "review_items": _sanitize_small_dicts(payload.get("review_items"), limit=20),
        "quality_gates_checked": _sanitize_string_list(payload.get("quality_gates_checked"), limit=20),
        "uncertainties": _sanitize_string_list(payload.get("uncertainties"), limit=20, max_chars=240),
        "next_actions": _sanitize_string_list(payload.get("next_actions"), limit=20, max_chars=240),
        "domain_payload": payload.get("domain_payload") if isinstance(payload.get("domain_payload"), dict) else {},
    }
    return ExpertReportV1.model_validate(data)


def _sanitize_expert_claims(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    claims: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        claim = {
            "claim_id": _clean_text(item.get("claim_id")),
            "text": _truncate(_scrub_text(item.get("text")), _MAX_CLAIM_TEXT_CHARS),
            "support_level": item.get("support_level"),
            "evidence_ids": _sanitize_string_list(item.get("evidence_ids"), limit=20),
            "citation_keys": _sanitize_string_list(item.get("citation_keys"), limit=20),
            "limitations": _sanitize_string_list(item.get("limitations"), limit=10, max_chars=180),
        }
        if claim["claim_id"] and claim["text"]:
            claims.append(claim)
        if len(claims) >= limit:
            break
    return claims


def _sanitize_expert_evidence(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    evidence: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        evidence_item = {
            "evidence_id": _clean_text(item.get("evidence_id")),
            "source_type": item.get("source_type"),
            "source_id": _optional_clean_text(item.get("source_id")),
            "citation_key": _optional_clean_text(item.get("citation_key")),
            "relevance": item.get("relevance"),
            "risk": item.get("risk"),
            "bounded_excerpt": _optional_truncated_scrubbed(
                item.get("bounded_excerpt"),
                _MAX_EVIDENCE_EXCERPT_CHARS,
            ),
            "used_for": _sanitize_string_list(item.get("used_for"), limit=20),
        }
        if evidence_item["evidence_id"]:
            evidence.append({key: val for key, val in evidence_item.items() if val is not None})
        if len(evidence) >= limit:
            break
    return evidence


def _sanitize_expert_artifacts(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    artifacts: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path = _optional_clean_text(item.get("path"))
        if not path or not _is_safe_ref_path(path):
            continue
        source_script = _optional_clean_text(item.get("source_script"))
        if source_script and not _is_safe_ref_path(source_script):
            source_script = None
        artifact = {
            "artifact_id": _clean_text(item.get("artifact_id")),
            "kind": _clean_text(item.get("kind")),
            "path": path,
            "source_script": source_script,
            "dataset_paths": [
                path_value
                for path_value in _sanitize_string_list(item.get("dataset_paths"), limit=10)
                if _is_safe_ref_path(path_value)
            ],
            "content_hash": _optional_clean_text(item.get("content_hash")),
            "caption": _optional_truncated_scrubbed(item.get("caption"), 240),
            "reviewable": item.get("reviewable", True) is not False,
        }
        if artifact["artifact_id"] and artifact["kind"]:
            artifacts.append({key: val for key, val in artifact.items() if val is not None})
        if len(artifacts) >= limit:
            break
    return artifacts


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


def _sanitize_string_list(value: Any, *, limit: int, max_chars: int = 120) -> list[str]:
    if not isinstance(value, list | tuple | set | frozenset):
        return []
    result: list[str] = []
    for item in value:
        text = _truncate(_scrub_text(item), max_chars)
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _sanitize_small_dicts(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            result.append({str(key): val for key, val in item.items() if isinstance(key, str)})
        if len(result) >= limit:
            break
    return result


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
