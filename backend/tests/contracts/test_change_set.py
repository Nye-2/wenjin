"""Tests for workspace ChangeSet public contracts."""

from __future__ import annotations

from pydantic import ValidationError

from src.contracts.change_set import ChangeSet


def _unit(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "id": "unit-1",
        "target": {
            "room": "documents",
            "object_type": "draft_section",
            "object_id": "doc-1",
            "section_id": "intro",
        },
        "action": "update",
        "risk": "low",
        "risk_reasons": [],
        "default_apply_state": "draft_applied",
        "requires_confirmation": False,
        "diff": {"before": "old", "after": "new"},
        "provenance": {"agent": "lead"},
        "rollback": {"restore": "old"},
    }
    data.update(overrides)
    return data


def _change_set(*units: dict[str, object]) -> ChangeSet:
    return ChangeSet(
        execution_id="exec-1",
        workspace_id="ws-1",
        write_mode="auto_draft",
        units=list(units) or [_unit()],
        summary="Apply a low-risk draft edit.",
        created_at="2026-07-06T00:00:00Z",
    )


def test_low_risk_draft_applied_change_set_round_trips() -> None:
    change_set = _change_set()

    dumped = change_set.model_dump(mode="json")
    round_tripped = ChangeSet.model_validate(dumped)

    assert round_tripped == change_set
    assert round_tripped.units[0].default_apply_state == "draft_applied"
    assert round_tripped.units[0].requires_confirmation is False


def test_high_risk_unit_without_risk_reason_is_rejected() -> None:
    try:
        _change_set(
            _unit(
                risk="high",
                risk_reasons=[],
                requires_confirmation=True,
                default_apply_state="staged",
            )
        )
    except ValidationError as exc:
        assert "risk_reasons" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected validation error")


def test_high_risk_unit_rejects_false_requires_confirmation() -> None:
    try:
        _change_set(
            _unit(
                risk="high",
                risk_reasons=["modifies a user-facing claim"],
                requires_confirmation=False,
                default_apply_state="staged",
            )
        )
    except ValidationError as exc:
        assert "requires_confirmation" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected validation error")


def test_high_risk_unit_rejects_draft_applied_default_state() -> None:
    try:
        _change_set(
            _unit(
                risk="high",
                risk_reasons=["modifies a user-facing claim"],
                requires_confirmation=True,
                default_apply_state="draft_applied",
            )
        )
    except ValidationError as exc:
        assert "default_apply_state" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected validation error")


def test_high_risk_unit_rejects_accepted_default_state() -> None:
    try:
        _change_set(
            _unit(
                risk="high",
                risk_reasons=["modifies a user-facing claim"],
                requires_confirmation=True,
                default_apply_state="accepted",
            )
        )
    except ValidationError as exc:
        assert "default_apply_state" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected validation error")


def test_blocked_unit_without_explanatory_reason_is_rejected() -> None:
    try:
        _change_set(_unit(default_apply_state="blocked", risk_reasons=[]))
    except ValidationError as exc:
        assert "blocked" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected validation error")


def test_multiple_units_with_different_targets_validate() -> None:
    change_set = _change_set(
        _unit(id="unit-1"),
        _unit(
            id="unit-2",
            target={
                "room": "library",
                "object_type": "reference",
                "object_id": "paper-1",
                "path": "/references/1",
            },
            action="create",
            risk="medium",
            default_apply_state="staged",
            diff={"after": {"title": "Example Paper"}},
            rollback={"delete": "paper-1"},
        ),
    )

    assert len(change_set.units) == 2
    assert change_set.units[0].target.room == "documents"
    assert change_set.units[1].target.room == "library"
    assert change_set.units[1].target.path == "/references/1"


def test_materialization_round_trips_for_output_unit() -> None:
    change_set = _change_set(
        _unit(
            provenance={"source": "task_report.outputs", "output_id": "dec-1"},
            materialization={
                "operation": "decisions.set",
                "payload": {
                    "key": "method",
                    "value": "qualitative",
                    "confidence": 1.0,
                },
            },
        )
    )

    dumped = change_set.model_dump(mode="json")
    round_tripped = ChangeSet.model_validate(dumped)

    assert round_tripped.units[0].materialization is not None
    assert round_tripped.units[0].materialization.operation == "decisions.set"
    assert round_tripped.units[0].materialization.payload["key"] == "method"


def test_output_unit_without_materialization_is_rejected() -> None:
    try:
        _change_set(
            _unit(
                provenance={"source": "task_report.outputs", "output_id": "doc-1"},
                materialization=None,
            )
        )
    except ValidationError as exc:
        assert "materialization" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected validation error")


def test_change_set_rejects_duplicate_unit_ids() -> None:
    try:
        _change_set(
            _unit(id="unit-1"),
            _unit(
                id="unit-1",
                target={
                    "room": "library",
                    "object_type": "reference",
                    "object_id": "paper-1",
                },
                action="create",
            ),
        )
    except ValidationError as exc:
        assert "duplicate" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected validation error")
