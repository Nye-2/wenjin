"""Pure policy for default workspace change apply states."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, cast, get_args

from pydantic import ValidationError

from src.contracts.change_set import (
    ApplyState,
    ChangeRisk,
    ChangeTarget,
    WriteMode,
    normalize_write_mode,
)

VALID_CHANGE_RISKS = set(get_args(ChangeRisk))
CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

SANDBOX_ROOM = "sandbox"
DOCUMENTS_ROOM = "documents"
MEMORY_ROOM = "memory"

HIGH_RISKS = frozenset({"high", "critical"})

TRUST_ROOMS = frozenset({"claims", "citations", "evidence", "review"})
TRUST_SUBJECT_TERMS = frozenset({"claim", "claims", "citation", "citations", "evidence"})
TRUST_MUTATION_TERMS = frozenset(
    {
        "accept",
        "accepted",
        "confirm",
        "confirmed",
        "reject",
        "rejected",
        "trust",
        "validate",
        "validated",
        "validation",
        "verify",
        "verified",
    }
)
SANDBOX_AUTO_OBJECT_TYPES = frozenset(
    {
        "artifact",
        "sandbox_artifact",
        "trace",
        "run_trace",
    }
)
DOCUMENT_DRAFT_OBJECT_TYPES = frozenset(
    {
        "draft",
        "document_draft",
        "draft_section",
        "section_draft",
    }
)


def decide_change_apply_state(
    *,
    mode: WriteMode | str | None,
    target: ChangeTarget | Mapping[str, Any],
    action: str,
    risk: ChangeRisk | str,
    reversible: bool,
    protected: bool = False,
    requires_confirmation: bool = False,
    provenance_backed: bool = False,
    system_owned: bool = False,
    review_only: bool = False,
) -> ApplyState:
    """Return the default apply state for a proposed workspace change.

    This policy is intentionally deterministic and side-effect free. It decides
    only the default state for review; callers remain responsible for creating
    ChangeUnits, presenting review UI, and applying any accepted writes.
    """

    write_mode = _normalize_mode(mode)
    change_risk = _normalize_risk(risk)
    change_target = _normalize_target(target)
    clean_action = str(action or "").strip()
    if not clean_action:
        raise ValueError("action must not be blank")

    room = change_target.room
    object_type = change_target.object_type

    if protected and room == DOCUMENTS_ROOM:
        return _blocked_or_staged_for_protected_document(change_risk)

    if _is_trust_mutation(change_target, clean_action):
        return _blocked_or_staged_for_review(change_risk, reversible, review_only)

    if _is_memory_fact(room, object_type) and not _is_system_owned_low_risk(
        change_risk,
        system_owned,
    ):
        return _blocked_or_staged_for_review(change_risk, reversible, review_only)

    if change_risk in HIGH_RISKS:
        return _blocked_or_staged_for_review(change_risk, reversible, review_only)

    if requires_confirmation:
        return "staged"

    if write_mode == "strict_review":
        return "staged"

    if write_mode == "ask_workspace_write":
        if _is_low_risk_reversible_sandbox_artifact(
            room=room,
            object_type=object_type,
            risk=change_risk,
            reversible=reversible,
            provenance_backed=provenance_backed,
        ):
            return "draft_applied"
        return "staged"

    if write_mode == "auto_draft":
        if _is_low_risk_reversible_sandbox_artifact(
            room=room,
            object_type=object_type,
            risk=change_risk,
            reversible=reversible,
            provenance_backed=provenance_backed,
        ):
            return "draft_applied"
        if _is_low_risk_reversible_document_draft(
            room=room,
            object_type=object_type,
            risk=change_risk,
            reversible=reversible,
        ):
            return "draft_applied"
        if _is_system_owned_low_risk(change_risk, system_owned) and reversible:
            return "draft_applied"
        return "staged"

    raise ValueError(f"Unhandled write_mode: {write_mode}")


def _normalize_mode(value: WriteMode | str | None) -> WriteMode:
    return normalize_write_mode(value)


def _normalize_risk(value: ChangeRisk | str) -> ChangeRisk:
    raw_value = str(value or "").strip()
    if raw_value in VALID_CHANGE_RISKS:
        return cast(ChangeRisk, raw_value)
    raise ValueError(f"Invalid risk: {value}. Must be one of: {sorted(VALID_CHANGE_RISKS)}")


def _normalize_target(target: ChangeTarget | Mapping[str, Any]) -> ChangeTarget:
    if isinstance(target, ChangeTarget):
        return target
    try:
        return ChangeTarget.model_validate(target)
    except ValidationError as exc:
        raise ValueError(f"Invalid target: {exc}") from exc


def _blocked_or_staged_for_protected_document(risk: ChangeRisk) -> ApplyState:
    if risk in HIGH_RISKS:
        return "blocked"
    return "staged"


def _blocked_or_staged_for_review(
    risk: ChangeRisk,
    reversible: bool,
    review_only: bool,
) -> ApplyState:
    if risk in HIGH_RISKS and not reversible and not review_only:
        return "blocked"
    return "staged"


def _is_trust_mutation(target: ChangeTarget, action: str) -> bool:
    if target.room in TRUST_ROOMS:
        return True

    action_terms = _split_policy_terms(action)
    target_terms = set[str]()
    for value in (target.object_type, target.path, target.section_id):
        target_terms.update(_split_policy_terms(value))

    all_terms = action_terms | target_terms
    has_trust_subject = bool(all_terms & TRUST_SUBJECT_TERMS)
    has_trust_mutation = bool(all_terms & TRUST_MUTATION_TERMS)

    return has_trust_subject and has_trust_mutation


def _is_memory_fact(room: str, object_type: str) -> bool:
    return room == MEMORY_ROOM and object_type in {"fact", "memory_fact"}


def _is_system_owned_low_risk(risk: ChangeRisk, system_owned: bool) -> bool:
    return system_owned and risk == "low"


def _is_low_risk_reversible_sandbox_artifact(
    *,
    room: str,
    object_type: str,
    risk: ChangeRisk,
    reversible: bool,
    provenance_backed: bool,
) -> bool:
    return (
        room == SANDBOX_ROOM
        and object_type in SANDBOX_AUTO_OBJECT_TYPES
        and risk == "low"
        and reversible
        and provenance_backed
    )


def _is_low_risk_reversible_document_draft(
    *,
    room: str,
    object_type: str,
    risk: ChangeRisk,
    reversible: bool,
) -> bool:
    return (
        room == DOCUMENTS_ROOM
        and object_type in DOCUMENT_DRAFT_OBJECT_TYPES
        and risk == "low"
        and reversible
    )


def _split_policy_terms(value: str | None) -> set[str]:
    separated = CAMEL_CASE_BOUNDARY.sub(" ", value or "")
    normalized = "".join(char.lower() if char.isalnum() else " " for char in separated)
    return {term for term in normalized.split() if term}
