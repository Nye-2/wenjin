"""Tests for server-side workspace change apply policy."""

from __future__ import annotations

import pytest

from src.contracts.change_set import ChangeTarget
from src.services.change_policy import decide_change_apply_state


def _target(room: str, object_type: str = "artifact") -> ChangeTarget:
    return ChangeTarget(room=room, object_type=object_type, object_id="obj-1")


@pytest.mark.parametrize(
    ("target", "action"),
    [
        (_target("sandbox", "artifact"), "create"),
        (_target("sandbox", "trace"), "append"),
    ],
)
def test_auto_draft_low_risk_reversible_sandbox_artifact_is_draft_applied(
    target: ChangeTarget,
    action: str,
) -> None:
    state = decide_change_apply_state(
        mode="auto_draft",
        target=target,
        action=action,
        risk="low",
        reversible=True,
        provenance_backed=True,
    )

    assert state == "draft_applied"


def test_auto_draft_low_risk_reversible_document_draft_is_draft_applied() -> None:
    state = decide_change_apply_state(
        mode="auto_draft",
        target=_target("documents", "draft_section"),
        action="update",
        risk="low",
        reversible=True,
    )

    assert state == "draft_applied"


@pytest.mark.parametrize(
    ("target", "action", "risk"),
    [
        (_target("documents", "draft_section"), "update_claim_trust", "low"),
        (_target("library", "citation_trust_record"), "update", "medium"),
        (
            ChangeTarget(
                room="documents",
                object_type="draft_section",
                object_id="doc-1",
                section_id="evidence:e1",
            ),
            "verify_evidence",
            "low",
        ),
        (
            ChangeTarget(
                room="documents",
                object_type="draft_section",
                object_id="doc-1",
                path="/citations/cite-1/trust",
            ),
            "update",
            "low",
        ),
    ],
)
def test_low_and_medium_trust_mutations_outside_trust_rooms_are_staged(
    target: ChangeTarget,
    action: str,
    risk: str,
) -> None:
    state = decide_change_apply_state(
        mode="auto_draft",
        target=target,
        action=action,
        risk=risk,
        reversible=True,
    )

    assert state == "staged"


@pytest.mark.parametrize("action", ["verifyEvidence", "updateClaimTrust"])
def test_camel_case_trust_actions_are_staged(action: str) -> None:
    state = decide_change_apply_state(
        mode="auto_draft",
        target=_target("documents", "draft_section"),
        action=action,
        risk="low",
        reversible=True,
    )

    assert state == "staged"


@pytest.mark.parametrize(
    "target",
    [
        ChangeTarget(
            room="documents",
            object_type="draft_section",
            object_id="doc-1",
            path="/review/evidenceTrust",
        ),
        ChangeTarget(
            room="documents",
            object_type="draft_section",
            object_id="doc-1",
            section_id="claimTrust",
        ),
        ChangeTarget(
            room="documents",
            object_type="draft_section",
            object_id="doc-1",
            path="/library/citationValidation",
        ),
    ],
)
def test_camel_case_trust_target_fields_are_staged(target: ChangeTarget) -> None:
    state = decide_change_apply_state(
        mode="auto_draft",
        target=target,
        action="update",
        risk="low",
        reversible=True,
    )

    assert state == "staged"


def test_embedded_trust_substrings_do_not_overmatch_ordinary_words() -> None:
    state = decide_change_apply_state(
        mode="auto_draft",
        target=_target("documents", "draft_section"),
        action="reclaimEntrustment",
        risk="low",
        reversible=True,
    )

    assert state == "draft_applied"


@pytest.mark.parametrize("room", ["claims", "evidence", "citations"])
def test_auto_draft_high_risk_trust_changes_are_not_draft_applied(room: str) -> None:
    state = decide_change_apply_state(
        mode="auto_draft",
        target=_target(room, "trust_record"),
        action="update",
        risk="high",
        reversible=True,
    )

    assert state in {"staged", "blocked"}
    assert state != "draft_applied"
    assert state != "accepted"


@pytest.mark.parametrize("room", ["documents", "library", "decisions", "tasks", "settings"])
def test_ask_workspace_write_durable_room_write_is_staged(room: str) -> None:
    state = decide_change_apply_state(
        mode="ask_workspace_write",
        target=_target(room, "record"),
        action="update",
        risk="low",
        reversible=True,
    )

    assert state == "staged"


def test_ask_workspace_write_low_risk_sandbox_artifact_is_draft_applied() -> None:
    state = decide_change_apply_state(
        mode="ask_workspace_write",
        target=_target("sandbox", "artifact"),
        action="create",
        risk="low",
        reversible=True,
        provenance_backed=True,
    )

    assert state == "draft_applied"


def test_strict_review_sandbox_artifact_is_staged() -> None:
    state = decide_change_apply_state(
        mode="strict_review",
        target=_target("sandbox", "artifact"),
        action="create",
        risk="low",
        reversible=True,
        provenance_backed=True,
    )

    assert state == "staged"


@pytest.mark.parametrize("mode", ["auto_draft", "ask_workspace_write", "strict_review"])
def test_memory_fact_requires_confirmation_in_all_modes(mode: str) -> None:
    state = decide_change_apply_state(
        mode=mode,
        target=_target("memory", "fact"),
        action="create",
        risk="low",
        reversible=True,
    )

    assert state == "staged"


@pytest.mark.parametrize("mode", ["auto_draft", "ask_workspace_write", "strict_review"])
def test_system_owned_low_risk_memory_fact_can_follow_mode_policy(mode: str) -> None:
    state = decide_change_apply_state(
        mode=mode,
        target=_target("memory", "fact"),
        action="create",
        risk="low",
        reversible=True,
        system_owned=True,
    )

    if mode == "auto_draft":
        assert state == "draft_applied"
    else:
        assert state == "staged"


def test_protected_document_change_does_not_auto_apply() -> None:
    state = decide_change_apply_state(
        mode="auto_draft",
        target=_target("documents", "draft_section"),
        action="update",
        risk="low",
        reversible=True,
        protected=True,
    )

    assert state == "staged"


def test_high_risk_protected_document_change_is_blocked() -> None:
    state = decide_change_apply_state(
        mode="auto_draft",
        target=_target("documents", "draft_section"),
        action="update",
        risk="high",
        reversible=True,
        protected=True,
    )

    assert state == "blocked"


def test_non_reversible_high_risk_review_only_change_is_staged() -> None:
    state = decide_change_apply_state(
        mode="auto_draft",
        target=_target("documents", "draft_section"),
        action="rewrite",
        risk="high",
        reversible=False,
        review_only=True,
    )

    assert state == "staged"


def test_non_reversible_high_risk_apply_requested_change_is_blocked() -> None:
    state = decide_change_apply_state(
        mode="auto_draft",
        target=_target("documents", "draft_section"),
        action="rewrite",
        risk="high",
        reversible=False,
        review_only=False,
    )

    assert state == "blocked"


def test_unknown_durable_room_is_conservative() -> None:
    state = decide_change_apply_state(
        mode="auto_draft",
        target=_target("custom_room", "record"),
        action="create",
        risk="low",
        reversible=True,
    )

    assert state == "staged"


@pytest.mark.parametrize(
    ("mode", "risk"),
    [
        ("surprise_mode", "low"),
        ("auto_draft", "surprise_risk"),
    ],
)
def test_invalid_mode_or_risk_raises(mode: str, risk: str) -> None:
    with pytest.raises(ValueError):
        decide_change_apply_state(
            mode=mode,
            target=_target("documents", "draft_section"),
            action="update",
            risk=risk,
            reversible=True,
        )


@pytest.mark.parametrize(
    "target",
    [
        {"room": "", "object_type": "draft_section"},
        {"room": "documents", "object_type": ""},
    ],
)
def test_invalid_target_raises(target: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        decide_change_apply_state(
            mode="auto_draft",
            target=target,
            action="update",
            risk="low",
            reversible=True,
        )
