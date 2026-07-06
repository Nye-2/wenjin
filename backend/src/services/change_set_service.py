"""Build reviewable workspace ChangeSets from execution TaskReports."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any, cast

from src.agents.contracts.task_report import (
    DecisionOutput,
    DocumentOutput,
    LibraryItemOutput,
    MemoryFactOutput,
    ResultOutput,
    ReviewPacketItem,
    TaskOutput,
    TaskReport,
)
from src.contracts.change_set import (
    ChangeMaterialization,
    ChangeRisk,
    ChangeSet,
    ChangeTarget,
    ChangeUnit,
    WriteMode,
    normalize_write_mode,
)
from src.services.change_policy import decide_change_apply_state

_HIGH_RISKS = {"high", "critical"}
_REVIEW_ONLY_ROOMS = {"review"}
_OUTPUT_KIND_ROOMS = {
    "library_item": "library",
    "document": "documents",
    "memory_fact": "memory",
    "decision": "decisions",
    "task": "tasks",
}
_OUTPUT_KIND_ACTIONS = {
    "library_item": "import",
    "document": "create",
    "memory_fact": "create",
    "decision": "record",
    "task": "create",
}
_OUTPUT_KIND_OBJECT_TYPES = {
    "library_item": "source",
    "memory_fact": "fact",
    "decision": "decision",
    "task": "task",
}
_TRUST_TERMS = {
    "claim",
    "claims",
    "citation",
    "citations",
    "evidence",
    "trust",
    "verify",
    "verified",
    "validation",
}
_SANDBOX_KINDS = {"sandbox_artifact", "artifact", "dataset"}
_PRISM_KINDS = {"prism_file_change", "prism_change"}
_SETTINGS_KINDS = {"setting", "settings", "workspace_settings"}
_WORKSPACE_SETTINGS_UPDATE_KEYS = frozenset(
    {
        "default_model",
        "thinking_enabled",
        "sandbox_provider",
        "auto_compact_threshold",
        "capability_overrides",
        "settings_json",
        "write_mode",
        "metadata_json",
    }
)
_MAX_INLINE_TEXT = 2_000
_MAX_CHANGE_UNITS = 200
_MAX_DICT_ITEMS = 40
_MAX_NESTING_DEPTH = 4
_MAX_MAPPING_BYTES = 24_000
_ID_HASH_LENGTH = 12
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_RISK_ORDER: dict[ChangeRisk, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_RISK_KEY_CANDIDATES = (
    "risk",
    "risk_level",
    "severity",
    "support_level",
    "support_state",
    "support_status",
    "status",
)
_NESTED_RISK_KEYS = (
    "semantic_contract",
    "academic_style_contract",
    "content_contract",
    "quality_contract",
    "risk",
)
_HIGH_SIGNAL_VALUES = {
    "blocked",
    "blocker",
    "critical",
    "evidence_gap",
    "fabricated",
    "failed",
    "high",
    "manual_review",
    "manual_review_required",
    "missing_evidence",
    "needs_review",
    "not_ready",
    "requires_manual_review",
    "unsupported",
    "unsupported_claim",
    "weak",
}
_MEDIUM_SIGNAL_VALUES = {
    "caution",
    "medium",
    "partial",
    "plausible",
    "review",
    "review_required",
    "unverified",
}
_LOW_SIGNAL_VALUES = {"complete", "low", "ok", "passed", "pending", "supported", "verified"}
_UNSAFE_BOOL_KEYS = {
    "citation_gap",
    "evidence_gap",
    "fabricated",
    "manual_review_required",
    "missing_evidence",
    "needs_review",
    "not_ready",
    "requires_manual_review",
    "unsupported_claim",
}


def build_change_set_from_task_report(
    report: TaskReport,
    *,
    workspace_id: str,
    write_mode: WriteMode | str | None,
) -> ChangeSet | None:
    """Return a ChangeSet projection for a report, or ``None`` when empty."""

    mode = normalize_write_mode(write_mode)
    units: list[ChangeUnit] = []
    seen_ids: set[str] = set()

    for output in report.outputs:
        _append_unique(units, _unit_from_output(output, mode=mode), seen_ids)

    for item in _review_packet_items(report):
        _append_unique(units, _unit_from_review_packet_item(item, mode=mode), seen_ids)

    for item in report.review_items:
        _append_unique(units, _unit_from_review_item_dict(item, mode=mode), seen_ids)

    if not units:
        return None
    omitted_count = max(0, len(units) - _MAX_CHANGE_UNITS)
    bounded_units = units[:_MAX_CHANGE_UNITS]

    return ChangeSet(
        execution_id=report.execution_id,
        workspace_id=workspace_id,
        write_mode=mode,
        units=bounded_units,
        summary=_summary_for_units(bounded_units, omitted_count=omitted_count),
        created_at=datetime.now(UTC).isoformat(),
    )


def _append_unique(
    units: list[ChangeUnit],
    unit: ChangeUnit | None,
    seen_ids: set[str],
) -> None:
    if unit is None:
        return
    unit_id = _unique_unit_id(unit.id, seen_ids)
    if unit_id != unit.id:
        unit = unit.model_copy(update={"id": unit_id})
    seen_ids.add(unit.id)
    units.append(unit)


def _unit_from_output(output: ResultOutput, *, mode: WriteMode) -> ChangeUnit:
    output_kind = output.kind
    room = _OUTPUT_KIND_ROOMS[output_kind]
    action = _OUTPUT_KIND_ACTIONS[output_kind]
    target = ChangeTarget(
        room=room,
        object_type=_object_type_for_output(output),
        object_id=_bounded_identifier(output.id, max_length=160, fallback=output_kind),
        path=_bounded_path(_path_for_output(output)),
    )
    risk, reasons, requires_confirmation = _risk_for_output(output)
    reversible = _output_is_reversible(output)
    protected = False
    provenance = {
        "source": "task_report.outputs",
        "output_id": output.id,
        "unit_source_id": _bounded_identifier(output.id, max_length=160, fallback=output_kind),
        "output_kind": output.kind,
    }
    state = decide_change_apply_state(
        mode=mode,
        target=target,
        action=action,
        risk=risk,
        reversible=reversible,
        protected=protected,
        requires_confirmation=requires_confirmation,
        provenance_backed=bool(provenance),
    )
    requires_confirmation = _final_requires_confirmation(
        state=state,
        requested=requires_confirmation,
    )
    return ChangeUnit(
        id=_unit_id("output", output.id),
        target=target,
        action=action,
        risk=risk,
        risk_reasons=reasons,
        default_apply_state=state,
        requires_confirmation=requires_confirmation,
        diff=_diff_for_output(output),
        provenance=provenance,
        rollback={
            "strategy": "delete_created_record" if reversible else "manual_review",
            "source_output_id": output.id,
        },
        materialization=_materialization_for_output(output),
    )


def _unit_from_review_packet_item(
    item: ReviewPacketItem,
    *,
    mode: WriteMode,
) -> ChangeUnit:
    payload = item.model_dump(mode="json")
    kind = str(item.kind)
    provenance = dict(item.provenance or {})
    target = _target_for_review_item(
        kind=kind,
        item_id=item.item_id,
        payload=payload,
        provenance=provenance,
    )
    risk, reasons = _risk_from_review_item_payload(
        kind=kind,
        payload=payload,
        default_checked=item.default_checked,
        can_commit=item.can_commit,
    )
    can_auto_draft = _is_auto_draftable_sandbox_item(
        kind=kind,
        target=target,
        provenance=provenance,
        payload=payload,
    )
    requires_confirmation = not can_auto_draft or not item.default_checked or not item.can_commit
    reversible = can_auto_draft
    protected = target.room == "documents"
    review_only = target.room in _REVIEW_ONLY_ROOMS and item.can_commit
    state = _state_for_review_item(
        mode=mode,
        target=target,
        action=_action_for_review_item(kind),
        risk=risk,
        reversible=reversible,
        protected=protected,
        requires_confirmation=requires_confirmation,
        provenance_backed=bool(provenance),
        review_only=review_only,
        can_commit=item.can_commit,
        risk_reasons=reasons,
    )
    return ChangeUnit(
        id=_unit_id("review", item.item_id),
        target=target,
        action=_action_for_review_item(kind),
        risk=risk,
        risk_reasons=reasons,
        default_apply_state=state,
        requires_confirmation=_final_requires_confirmation(
            state=state,
            requested=requires_confirmation,
        ),
        diff=_bounded_mapping(
            {
                "title": item.title,
                "summary": item.summary,
                "preview": item.preview,
                "claim_refs": item.claim_refs,
                "evidence_refs": item.evidence_refs,
                "artifact_refs": item.artifact_refs,
                "quality_surfaces": item.quality_surfaces,
            }
        ),
        provenance=provenance or {"source": "task_report.review_packet"},
        rollback={
            "strategy": "delete_created_record" if reversible else "manual_review",
            "source_review_item_id": item.item_id,
        },
        materialization=_materialization_for_review_item(
            target=target,
            payload=payload,
            item_id=item.item_id,
        ),
    )


def _unit_from_review_item_dict(
    item: Any,
    *,
    mode: WriteMode,
) -> ChangeUnit | None:
    if not isinstance(item, Mapping):
        return None
    payload = dict(item)
    item_id = _clean_text(payload.get("id") or payload.get("item_id"))
    if not item_id:
        return None
    kind = _clean_text(payload.get("kind") or payload.get("target_kind") or "review_item")
    provenance = _provenance_from_review_item_payload(payload)
    target = _target_for_review_item(
        kind=kind,
        item_id=item_id,
        payload=payload,
        provenance=provenance,
    )
    can_commit = _review_item_can_commit(payload)
    default_checked = bool(payload.get("default_checked", can_commit))
    risk, reasons = _risk_from_review_item_payload(
        kind=kind,
        payload=payload,
        default_checked=default_checked,
        can_commit=can_commit,
    )
    can_auto_draft = _is_auto_draftable_sandbox_item(
        kind=kind,
        target=target,
        provenance=provenance,
        payload=payload,
    )
    requires_confirmation = not can_auto_draft or not default_checked or not can_commit
    reversible = can_auto_draft
    protected = target.room == "documents"
    review_only = target.room in _REVIEW_ONLY_ROOMS and can_commit
    action = _action_for_review_item(kind)
    state = _state_for_review_item(
        mode=mode,
        target=target,
        action=action,
        risk=risk,
        reversible=reversible,
        protected=protected,
        requires_confirmation=requires_confirmation,
        provenance_backed=bool(provenance),
        review_only=review_only,
        can_commit=can_commit,
        risk_reasons=reasons,
    )
    return ChangeUnit(
        id=_unit_id("review", item_id),
        target=target,
        action=action,
        risk=risk,
        risk_reasons=reasons,
        default_apply_state=state,
        requires_confirmation=_final_requires_confirmation(
            state=state,
            requested=requires_confirmation,
        ),
        diff=_bounded_mapping(
            {
                "title": payload.get("title"),
                "summary": payload.get("summary"),
                "target": payload.get("target"),
                "preview": payload.get("preview"),
                "status": payload.get("status"),
            }
        ),
        provenance=provenance or {"source": "task_report.review_items"},
        rollback={
            "strategy": "delete_created_record" if reversible else "manual_review",
            "source_review_item_id": item_id,
        },
        materialization=_materialization_for_review_item(
            target=target,
            payload=payload,
            item_id=item_id,
        ),
    )


def _state_for_review_item(
    *,
    mode: WriteMode,
    target: ChangeTarget,
    action: str,
    risk: ChangeRisk,
    reversible: bool,
    protected: bool,
    requires_confirmation: bool,
    provenance_backed: bool,
    review_only: bool,
    can_commit: bool,
    risk_reasons: list[str],
) -> str:
    if not can_commit:
        if "cannot be committed" not in risk_reasons:
            risk_reasons.append("cannot be committed")
        return "blocked"
    return decide_change_apply_state(
        mode=mode,
        target=target,
        action=action,
        risk=risk,
        reversible=reversible,
        protected=protected,
        requires_confirmation=requires_confirmation,
        provenance_backed=provenance_backed,
        review_only=review_only,
    )


def _review_packet_items(report: TaskReport) -> Iterable[ReviewPacketItem]:
    packet = report.review_packet
    if packet is None:
        return ()
    return packet.items


def _object_type_for_output(output: ResultOutput) -> str:
    if isinstance(output, DocumentOutput):
        doc_kind = _clean_text(output.data.doc_kind).lower()
        if "draft" in doc_kind:
            return "document_draft"
        return "document"
    return _OUTPUT_KIND_OBJECT_TYPES[output.kind]


def _path_for_output(output: ResultOutput) -> str | None:
    if isinstance(output, DocumentOutput):
        return output.data.storage_path or output.data.name
    if isinstance(output, LibraryItemOutput):
        return output.data.doi or output.data.url or output.data.external_id
    if isinstance(output, DecisionOutput):
        return output.data.key
    return None


def _risk_for_output(output: ResultOutput) -> tuple[ChangeRisk, list[str], bool]:
    reasons: list[str] = []
    requires_confirmation = False
    risk: ChangeRisk = "low"

    if not output.default_checked:
        risk = "medium"
        reasons.append("output is unchecked by default")
        requires_confirmation = True

    if isinstance(output, LibraryItemOutput):
        risk = _max_risk(risk, "medium")
        reasons.append("library source should be reviewed before saving")
        requires_confirmation = True
    elif isinstance(output, MemoryFactOutput):
        reasons.append("memory facts require user review")
        requires_confirmation = True
    elif isinstance(output, DecisionOutput):
        risk = _max_risk(risk, "medium")
        reasons.append("workspace decisions require user review")
        requires_confirmation = True
    elif isinstance(output, DocumentOutput):
        reasons.append("document writes require review before saving")
        requires_confirmation = True
        if _contains_trust_terms(output.data.doc_kind, output.data.name, output.preview):
            risk = _max_risk(risk, "medium")
            reasons.append("document content touches claims, citations, or evidence")

    return risk, _unique_strings(reasons), requires_confirmation


def _output_is_reversible(output: ResultOutput) -> bool:
    if isinstance(output, DocumentOutput):
        return True
    if isinstance(output, TaskOutput):
        return True
    if isinstance(output, LibraryItemOutput):
        return True
    return False


def _diff_for_output(output: ResultOutput) -> dict[str, Any]:
    if isinstance(output, DocumentOutput):
        data = output.data
        return _bounded_mapping(
            {
                "op": "create",
                "name": data.name,
                "doc_kind": data.doc_kind,
                "mime_type": data.mime_type,
                "storage_path": data.storage_path,
                "content_excerpt": data.content,
                "content_chars": len(data.content or ""),
                "preview": output.preview,
            }
        )
    return _bounded_mapping(
        {
            "op": _OUTPUT_KIND_ACTIONS[output.kind],
            "preview": output.preview,
            "data": output.data.model_dump(mode="json"),
        }
    )


def _materialization_for_output(output: ResultOutput) -> ChangeMaterialization:
    data = output.data.model_dump(mode="json")
    if isinstance(output, LibraryItemOutput):
        return ChangeMaterialization(
            operation="library.import_source",
            payload=_bounded_mapping(data),
        )
    if isinstance(output, DocumentOutput):
        return ChangeMaterialization(
            operation="documents.upsert_prism_file",
            payload=_bounded_mapping(
                {
                    "name": output.data.name,
                    "doc_kind": output.data.doc_kind,
                    "mime_type": output.data.mime_type,
                    "storage_path": output.data.storage_path,
                    "content_inline": output.data.content,
                    "size_bytes": output.data.size_bytes,
                }
            ),
        )
    if isinstance(output, MemoryFactOutput):
        return ChangeMaterialization(
            operation="memory.merge_items",
            payload=_bounded_mapping(
                {
                    "items": [
                        {
                            "category": output.data.category,
                            "content": output.data.content,
                            "confidence": output.data.confidence,
                        }
                    ]
                }
            ),
        )
    if isinstance(output, DecisionOutput):
        return ChangeMaterialization(
            operation="decisions.set",
            payload=_bounded_mapping(
                {
                    "key": output.data.key,
                    "value": output.data.value,
                    "confidence": output.data.confidence,
                }
            ),
        )
    if isinstance(output, TaskOutput):
        return ChangeMaterialization(
            operation="tasks.create",
            payload=_bounded_mapping(
                {
                    "title": output.data.title,
                    "description": output.data.description,
                    "priority": output.data.priority,
                }
            ),
        )
    raise ValueError(f"Unsupported output kind for materialization: {output.kind}")


def _materialization_for_review_item(
    *,
    target: ChangeTarget,
    payload: Mapping[str, Any],
    item_id: str,
) -> ChangeMaterialization | None:
    if target.room == "settings":
        settings_payload = _settings_update_payload_for_review_item(payload)
        if settings_payload is None:
            return None
        return ChangeMaterialization(
            operation="settings.update",
            payload=settings_payload,
        )
    if target.room != "sandbox":
        return None
    artifact_id = _first_non_empty(
        _nested_get(payload, "target", "sandbox_artifact_id"),
        _nested_get(payload, "preview", "sandbox_artifact_id"),
        _nested_get(payload, "source", "sandbox_artifact_id"),
        _nested_get(payload, "provenance", "sandbox_artifact_id"),
    )
    if not artifact_id:
        return None
    path = _bounded_path(
        _first_non_empty(
            _nested_get(payload, "target", "path"),
            _nested_get(payload, "preview", "path"),
            target.path,
        )
    )
    materialization_payload = {
        "artifact_id": artifact_id,
        "review_item_id": item_id,
    }
    if path:
        materialization_payload["path"] = path
    return ChangeMaterialization(
        operation="sandbox.materialize_artifact",
        payload=materialization_payload,
    )


def _settings_update_payload_for_review_item(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    update_source = _first_mapping(
        payload.get("updates"),
        payload.get("settings"),
        _nested_get(payload, "target", "updates"),
        _nested_get(payload, "target", "settings"),
    )
    if update_source is None:
        update_source = payload
    update_payload = {
        key: update_source[key]
        for key in _WORKSPACE_SETTINGS_UPDATE_KEYS
        if key in update_source and update_source[key] is not None
    }
    return _bounded_mapping(update_payload) if update_payload else None


def _target_for_review_item(
    *,
    kind: str,
    item_id: str,
    payload: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> ChangeTarget:
    target_payload = payload.get("target")
    target = dict(target_payload) if isinstance(target_payload, Mapping) else {}
    preview_payload = payload.get("preview")
    preview = dict(preview_payload) if isinstance(preview_payload, Mapping) else {}

    if kind in _SETTINGS_KINDS:
        return ChangeTarget(
            room="settings",
            object_type="workspace_settings",
            object_id=_bounded_identifier(
                target.get("setting_key") or target.get("key") or payload.get("setting_key") or item_id,
                max_length=160,
                fallback=kind,
            ),
        )
    if kind in _SANDBOX_KINDS or _looks_like_sandbox(provenance, payload):
        return ChangeTarget(
            room="sandbox",
            object_type="sandbox_artifact" if kind == "sandbox_artifact" else "artifact",
            object_id=_bounded_identifier(
                target.get("sandbox_artifact_id") or item_id,
                max_length=160,
                fallback=kind,
            ),
            path=_bounded_path(target.get("path") or preview.get("path")),
        )
    if kind in _PRISM_KINDS:
        return ChangeTarget(
            room="documents",
            object_type="draft_section",
            object_id=_bounded_identifier(
                target.get("logical_key") or payload.get("logical_key") or item_id,
                max_length=160,
                fallback=kind,
            ),
            path=_bounded_path(target.get("file_path") or target.get("path") or preview.get("path")),
        )
    if kind == "document":
        return ChangeTarget(
            room="documents",
            object_type="document_draft",
            object_id=_bounded_identifier(item_id, max_length=160, fallback=kind),
            path=_bounded_path(
                _first_non_empty(
                    preview.get("path"),
                    target.get("path"),
                    _first_string(payload.get("artifact_refs")),
                )
            ),
        )
    if kind == "memory":
        return ChangeTarget(
            room="memory",
            object_type="fact",
            object_id=_bounded_identifier(item_id, max_length=160, fallback=kind),
        )
    if kind == "decision":
        return ChangeTarget(
            room="decisions",
            object_type="decision",
            object_id=_bounded_identifier(item_id, max_length=160, fallback=kind),
        )
    if kind == "task":
        return ChangeTarget(
            room="tasks",
            object_type="task",
            object_id=_bounded_identifier(item_id, max_length=160, fallback=kind),
        )
    if kind == "reference":
        return ChangeTarget(
            room="library",
            object_type="source",
            object_id=_bounded_identifier(item_id, max_length=160, fallback=kind),
        )
    return ChangeTarget(
        room="review",
        object_type=_bounded_identifier(kind or "review_item", max_length=80, fallback="review_item"),
        object_id=_bounded_identifier(item_id, max_length=160, fallback=kind or "review_item"),
    )


def _risk_from_review_item_payload(
    *,
    kind: str,
    payload: Mapping[str, Any],
    default_checked: bool,
    can_commit: bool,
) -> tuple[ChangeRisk, list[str]]:
    risk, reasons = _extract_payload_risk(payload)

    if kind in _PRISM_KINDS:
        risk = _max_risk(risk, "medium")
        reasons.append("Prism file changes alter manuscript content")
    elif kind in {"warning"}:
        risk = _max_risk(risk, "high")
        reasons.append("review warning requires manual resolution")
    elif kind in {"memory", "decision", "reference"}:
        risk = _max_risk(risk, "medium")
        reasons.append(f"{kind} review item writes durable workspace state")

    if _payload_contains_trust_terms(payload):
        risk = _max_risk(risk, "medium")
        reasons.append("item touches claims, citations, evidence, or trust state")
    if not default_checked:
        risk = _max_risk(risk, "medium")
        reasons.append("item is unchecked by default")
    if not can_commit:
        risk = _max_risk(risk, "high")
        reasons.append("cannot be committed")
    if risk in _HIGH_RISKS and not reasons:
        reasons.append("high risk review item")
    return risk, _unique_strings(reasons)


def _extract_payload_risk(payload: Mapping[str, Any]) -> tuple[ChangeRisk, list[str]]:
    risk: ChangeRisk = "low"
    reasons: list[str] = _unique_strings(
        payload.get("risk_reasons") or payload.get("reasons") or payload.get("reason") or []
    )
    for key in _RISK_KEY_CANDIDATES:
        next_risk, next_reasons = _risk_from_raw_signal(key, payload.get(key))
        risk = _max_risk(risk, next_risk)
        reasons.extend(next_reasons)

    preview = payload.get("preview")
    if isinstance(preview, Mapping):
        nested_risk, nested_reasons = _extract_nested_contract_risk(preview)
        risk = _max_risk(risk, nested_risk)
        reasons.extend(nested_reasons)

    for key in _UNSAFE_BOOL_KEYS:
        if payload.get(key) is True:
            risk = _max_risk(risk, "high")
            reasons.append(key)
    return risk, _unique_strings(reasons)


def _extract_nested_contract_risk(mapping: Mapping[str, Any], *, depth: int = 0) -> tuple[ChangeRisk, list[str]]:
    if depth >= _MAX_NESTING_DEPTH:
        return "low", []
    risk: ChangeRisk = "low"
    reasons: list[str] = _unique_strings(mapping.get("reasons") or mapping.get("reason") or [])
    for key, value in mapping.items():
        key_text = str(key or "")
        if key_text in _RISK_KEY_CANDIDATES:
            next_risk, next_reasons = _risk_from_raw_signal(key_text, value)
            risk = _max_risk(risk, next_risk)
            reasons.extend(next_reasons)
            continue
        if key_text in _UNSAFE_BOOL_KEYS and value is True:
            risk = _max_risk(risk, "high")
            reasons.append(key_text)
        if key_text in _NESTED_RISK_KEYS and isinstance(value, Mapping):
            next_risk, next_reasons = _extract_nested_contract_risk(value, depth=depth + 1)
            risk = _max_risk(risk, next_risk)
            reasons.extend(next_reasons)
    return risk, _unique_strings(reasons)


def _risk_from_raw_signal(key: str, value: Any) -> tuple[ChangeRisk, list[str]]:
    if isinstance(value, Mapping):
        risk: ChangeRisk = "low"
        reasons = _unique_strings(value.get("reasons") or value.get("reason") or [])
        for candidate_key in ("level", "risk", "risk_level", "severity", "status", "support_level"):
            next_risk, next_reasons = _risk_from_raw_signal(candidate_key, value.get(candidate_key))
            risk = _max_risk(risk, next_risk)
            reasons.extend(next_reasons)
        for unsafe_key in _UNSAFE_BOOL_KEYS:
            if value.get(unsafe_key) is True:
                risk = _max_risk(risk, "high")
                reasons.append(unsafe_key)
        return risk, _unique_strings(reasons)

    if isinstance(value, bool):
        if value and key in _UNSAFE_BOOL_KEYS:
            return "high", [key]
        return "low", []

    normalized = _signal_terms(value)
    if not normalized:
        return "low", []
    if normalized & _HIGH_SIGNAL_VALUES:
        return "critical" if "critical" in normalized else "high", [_clean_text(value)]
    if normalized & _MEDIUM_SIGNAL_VALUES:
        return "medium", [_clean_text(value)]
    if normalized & _LOW_SIGNAL_VALUES:
        return "low", []
    return _normalize_risk(_clean_text(value), fallback="low"), []


def _action_for_review_item(kind: str) -> str:
    if kind in _SANDBOX_KINDS:
        return "accept_sandbox_artifact"
    if kind in _PRISM_KINDS:
        return "apply_prism_change"
    if kind == "warning":
        return "resolve_warning"
    return "review"


def _provenance_from_review_item_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    provenance: dict[str, Any] = {}
    for key in ("source", "reproducibility", "provenance"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            provenance[key] = dict(value)
    if not provenance:
        return {}
    return _bounded_mapping(provenance)


def _review_item_can_commit(payload: Mapping[str, Any]) -> bool:
    if "can_commit" in payload:
        return bool(payload.get("can_commit"))
    status = _clean_text(payload.get("status")).lower()
    if status in {"blocked", "failed", "rejected"}:
        return False
    actions = payload.get("actions")
    if isinstance(actions, list):
        action_names = {
            _clean_text(action.get("action")).lower()
            for action in actions
            if isinstance(action, Mapping)
        }
        if action_names:
            return bool(
                action_names
                & {
                    "accept_sandbox_artifact",
                    "apply_prism_change",
                    "accept",
                    "apply",
                }
            )
    return True


def _is_auto_draftable_sandbox_item(
    *,
    kind: str,
    target: ChangeTarget,
    provenance: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> bool:
    return (
        (kind in _SANDBOX_KINDS or target.room == "sandbox")
        and target.room == "sandbox"
        and bool(provenance or payload.get("provenance"))
    )


def _looks_like_sandbox(provenance: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    text = " ".join(
        _clean_text(value)
        for value in (
            provenance.get("source_kind"),
            provenance.get("source_id"),
            _nested_get(provenance, "source", "type"),
            _nested_get(payload, "source", "type"),
            _nested_get(payload, "target", "kind"),
        )
    ).lower()
    return "sandbox" in text


def _payload_contains_trust_terms(payload: Mapping[str, Any]) -> bool:
    if any(payload.get(key) for key in ("claim_refs", "evidence_refs")):
        return True
    target = payload.get("target")
    preview = payload.get("preview")
    values = [
        payload.get("kind"),
        payload.get("title"),
        payload.get("summary"),
    ]
    if isinstance(target, Mapping):
        values.extend(target.values())
    if isinstance(preview, Mapping):
        values.extend(preview.values())
    return _contains_trust_terms(*values)


def _contains_trust_terms(*values: Any) -> bool:
    terms: set[str] = set()
    for value in values:
        terms.update(_signal_terms(value))
    return bool(terms & _TRUST_TERMS)


def _signal_terms(value: Any) -> set[str]:
    separated = _CAMEL_CASE_BOUNDARY.sub(" ", _clean_text(value))
    normalized = "".join(char.lower() if char.isalnum() else " " for char in separated)
    return {term for term in normalized.split() if term}


def _normalize_risk(value: Any, *, fallback: ChangeRisk) -> ChangeRisk:
    raw = _clean_text(value)
    if raw in {"low", "medium", "high", "critical"}:
        return cast(ChangeRisk, raw)
    return fallback


def _max_risk(left: ChangeRisk, right: ChangeRisk) -> ChangeRisk:
    return left if _RISK_ORDER[left] >= _RISK_ORDER[right] else right


def _final_requires_confirmation(*, state: str, requested: bool) -> bool:
    return requested or state in {"staged", "blocked"}


def _summary_for_units(units: list[ChangeUnit], *, omitted_count: int = 0) -> str:
    counts = {
        "draft_applied": 0,
        "staged": 0,
        "blocked": 0,
        "accepted": 0,
        "rejected": 0,
        "undone": 0,
    }
    for unit in units:
        counts[unit.default_apply_state] += 1
    pieces = [
        f"{len(units)} change units",
        f"{counts['draft_applied']} draft-applied",
        f"{counts['staged']} staged",
        f"{counts['blocked']} blocked",
    ]
    if omitted_count > 0:
        pieces.append(f"{omitted_count} omitted from preview")
    return ", ".join(pieces)


def _bounded_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    bounded = dict(_bounded_json(dict(value), depth=0))
    size = _json_size(bounded)
    if size <= _MAX_MAPPING_BYTES:
        return bounded
    summary = _first_non_empty(
        bounded.get("title"),
        bounded.get("summary"),
        bounded.get("path"),
        bounded.get("name"),
    )
    return {
        "_truncated": True,
        "approx_bytes": size,
        "summary": summary or "payload omitted because it exceeded the ChangeSet preview budget",
    }


def _bounded_json(value: Any, *, depth: int) -> Any:
    if depth >= _MAX_NESTING_DEPTH:
        return "[nested payload truncated]"
    if isinstance(value, str):
        if len(value) <= _MAX_INLINE_TEXT:
            return value
        return f"{value[:_MAX_INLINE_TEXT]}... [truncated {len(value) - _MAX_INLINE_TEXT} chars]"
    if isinstance(value, Mapping):
        items = list(value.items())
        bounded_items = items[:_MAX_DICT_ITEMS]
        result = {
            str(key): _bounded_json(item, depth=depth + 1)
            for key, item in bounded_items
            if item is not None
        }
        if len(items) > _MAX_DICT_ITEMS:
            result["_omitted_keys"] = len(items) - _MAX_DICT_ITEMS
        return result
    if isinstance(value, list):
        items = [_bounded_json(item, depth=depth + 1) for item in value[:50]]
        if len(value) > 50:
            items.append(f"[truncated {len(value) - 50} items]")
        return items
    if isinstance(value, tuple | set | frozenset):
        values = list(value)
        items = [_bounded_json(item, depth=depth + 1) for item in values[:50]]
        if len(values) > 50:
            items.append(f"[truncated {len(values) - 50} items]")
        return items
    return value


def _json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except Exception:
        return _MAX_MAPPING_BYTES + 1


def _unit_id(prefix: str, raw_id: Any) -> str:
    clean_prefix = _bounded_identifier(prefix, max_length=32, fallback="unit")
    suffix = _bounded_identifier(
        raw_id,
        max_length=160 - len(clean_prefix) - 1,
        fallback="item",
    )
    return f"{clean_prefix}-{suffix}"


def _bounded_identifier(value: Any, *, max_length: int, fallback: str) -> str:
    text = _clean_text(value) or fallback
    if len(text) <= max_length:
        return text
    digest = _stable_hash(text)
    keep = max(1, max_length - _ID_HASH_LENGTH - 1)
    return f"{text[:keep]}-{digest}"


def _bounded_path(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    return _bounded_identifier(text, max_length=500, fallback="path")


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:_ID_HASH_LENGTH]


def _unique_unit_id(unit_id: str, seen: set[str]) -> str:
    if unit_id not in seen:
        return unit_id
    index = 2
    suffix = f"-{index}"
    base = _bounded_identifier(
        unit_id,
        max_length=160 - len(suffix),
        fallback="unit",
    )
    while f"{base}{suffix}" in seen:
        index += 1
        suffix = f"-{index}"
        base = _bounded_identifier(
            unit_id,
            max_length=160 - len(suffix),
            fallback="unit",
        )
    return f"{base}{suffix}"


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    if not isinstance(values, Iterable) or isinstance(values, str | bytes):
        values = [values]
    for value in values:
        text = _clean_text(value)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _first_string(values: Any) -> str | None:
    if isinstance(values, list | tuple):
        for value in values:
            text = _clean_text(value)
            if text:
                return text
    return None


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return None


def _first_mapping(*values: Any) -> Mapping[str, Any] | None:
    for value in values:
        if isinstance(value, Mapping):
            return value
    return None


def _nested_get(mapping: Mapping[str, Any], *keys: str) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _clean_text(value: Any) -> str:
    return str(value or "").strip()
