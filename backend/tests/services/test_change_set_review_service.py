"""Tests for ChangeSet review-state mutations."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.contracts.change_set import ChangeSet, ChangeTarget, ChangeUnit
from src.services.change_set_review_service import (
    ChangeSetReviewNotFoundError,
    ChangeSetReviewPersistenceError,
    ChangeSetReviewService,
)


def _unit(
    unit_id: str,
    *,
    state: str = "staged",
    risk: str = "low",
    reasons: list[str] | None = None,
) -> ChangeUnit:
    return ChangeUnit(
        id=unit_id,
        target=ChangeTarget(room="sandbox", object_type="artifact", object_id=unit_id),
        action="review",
        risk=risk,
        risk_reasons=reasons or [],
        default_apply_state=state,
        requires_confirmation=state != "draft_applied",
        diff={},
        provenance={},
        rollback={},
    )


def _change_set() -> dict:
    return ChangeSet(
        execution_id="exec-1",
        workspace_id="ws-1",
        write_mode="auto_draft",
        units=[
            _unit("unit-1", state="staged"),
            _unit("unit-2", state="draft_applied"),
            _unit(
                "unit-blocked",
                state="blocked",
                risk="high",
                reasons=["unsafe evidence change"],
            ),
        ],
        summary="3 change units",
        created_at="2026-07-06T00:00:00+00:00",
    ).model_dump(mode="json")


def _execution_service(
    *,
    result: dict | None = None,
    user_id: str = "user-1",
    persisted_result: dict | None = None,
) -> AsyncMock:
    svc = AsyncMock()
    svc.get_by_id.return_value = SimpleNamespace(
        id="exec-1",
        workspace_id="ws-1",
        user_id=user_id,
        result=result if result is not None else {"change_set": _change_set()},
    )

    async def _patch_execution_result(execution_id: str, *, result_patch: dict, commit: bool):
        _ = execution_id, commit
        base_result = result if result is not None else {"change_set": _change_set()}
        return SimpleNamespace(
            id="exec-1",
            workspace_id="ws-1",
            user_id=user_id,
            result=persisted_result if persisted_result is not None else {**base_result, **result_patch},
        )

    svc.patch_execution_result = AsyncMock(side_effect=_patch_execution_result)
    return svc


@pytest.mark.asyncio
async def test_get_change_set_returns_effective_default_states() -> None:
    svc = _execution_service()
    service = ChangeSetReviewService(execution_service=svc)

    response = await service.get_change_set("exec-1", actor_user_id="user-1")

    assert response["change_set"]["execution_id"] == "exec-1"
    assert response["review_state"]["accepted_unit_ids"] == []
    assert {item["unit_id"]: item["state"] for item in response["unit_states"]} == {
        "unit-1": "staged",
        "unit-2": "draft_applied",
        "unit-blocked": "blocked",
    }


@pytest.mark.asyncio
async def test_accept_units_persists_review_state() -> None:
    svc = _execution_service()
    service = ChangeSetReviewService(execution_service=svc)

    response = await service.accept_units(
        "exec-1",
        unit_ids=["unit-1", "unit-1"],
        actor_user_id="user-1",
    )

    result = svc.patch_execution_result.await_args.kwargs["result_patch"]
    assert result["change_set_review_state"]["accepted_unit_ids"] == ["unit-1"]
    assert response["unit_states"][0]["state"] == "accepted"


@pytest.mark.asyncio
async def test_accept_units_merges_into_latest_result_payload() -> None:
    svc = _execution_service(result={"change_set": _change_set()})
    persisted_results: list[dict] = []

    async def _patch_execution_result(execution_id: str, *, result_patch: dict, commit: bool):
        _ = execution_id, commit
        persisted_result = {
            "change_set": _change_set(),
            "commit_state": {
                "status": "committed",
                "accepted_ids": ["out-1"],
                "rejected_ids": [],
                "counts": {},
                "room_targets": {},
            },
            **result_patch,
        }
        persisted_results.append(persisted_result)
        return SimpleNamespace(
            id="exec-1",
            workspace_id="ws-1",
            user_id="user-1",
            result=persisted_result,
        )

    svc.patch_execution_result = AsyncMock(side_effect=_patch_execution_result)
    service = ChangeSetReviewService(execution_service=svc)

    await service.accept_units("exec-1", unit_ids=["unit-1"], actor_user_id="user-1")

    patch = svc.patch_execution_result.await_args.kwargs["result_patch"]
    assert patch["change_set_review_state"]["accepted_unit_ids"] == ["unit-1"]
    assert persisted_results[0]["commit_state"]["status"] == "committed"
    assert persisted_results[0]["change_set_review_state"]["accepted_unit_ids"] == ["unit-1"]


@pytest.mark.asyncio
async def test_accept_units_uses_atomic_result_patch_when_available() -> None:
    svc = _execution_service()
    async def _patch_execution_result(execution_id: str, *, result_patch: dict, commit: bool):
        _ = execution_id, commit
        persisted_result = {
            "change_set": _change_set(),
            "commit_state": {
                "status": "committed",
                "accepted_ids": ["out-1"],
                "rejected_ids": [],
                "counts": {},
                "room_targets": {},
            },
            **result_patch,
        }
        return SimpleNamespace(
            id="exec-1",
            workspace_id="ws-1",
            user_id="user-1",
            result=persisted_result,
        )

    svc.patch_execution_result = AsyncMock(side_effect=_patch_execution_result)
    service = ChangeSetReviewService(execution_service=svc)

    response = await service.accept_units("exec-1", unit_ids=["unit-1"], actor_user_id="user-1")

    svc.patch_execution_result.assert_awaited_once()
    patch_kwargs = svc.patch_execution_result.await_args.kwargs
    assert patch_kwargs["result_patch"]["change_set_review_state"]["accepted_unit_ids"] == ["unit-1"]
    svc.update_execution.assert_not_awaited()
    assert response["review_state"]["accepted_unit_ids"] == ["unit-1"]


@pytest.mark.asyncio
async def test_accept_units_requires_locked_patch_support() -> None:
    svc = AsyncMock()
    svc.get_by_id.return_value = SimpleNamespace(
        id="exec-1",
        workspace_id="ws-1",
        user_id="user-1",
        result={"change_set": _change_set()},
    )
    service = ChangeSetReviewService(execution_service=svc)

    with pytest.raises(ChangeSetReviewPersistenceError, match="locked result patch support"):
        await service.accept_units("exec-1", unit_ids=["unit-1"], actor_user_id="user-1")

    svc.update_execution.assert_not_awaited()


@pytest.mark.asyncio
async def test_repeating_accept_is_idempotent_and_does_not_rewrite() -> None:
    review_state = {
        "schema_version": "wenjin.change_set.review_state.v1",
        "accepted_unit_ids": ["unit-1"],
        "rejected_unit_ids": [],
        "undone_unit_ids": [],
        "updated_at": "2026-07-06T00:00:00+00:00",
    }
    svc = _execution_service(result={"change_set": _change_set(), "change_set_review_state": review_state})
    service = ChangeSetReviewService(execution_service=svc)

    response = await service.accept_units("exec-1", unit_ids=["unit-1"], actor_user_id="user-1")

    svc.patch_execution_result.assert_not_awaited()
    assert response["review_state"]["updated_at"] == "2026-07-06T00:00:00+00:00"
    assert response["unit_states"][0]["state"] == "accepted"


@pytest.mark.asyncio
async def test_reject_clears_previous_acceptance() -> None:
    review_state = {
        "accepted_unit_ids": ["unit-1"],
        "rejected_unit_ids": [],
        "undone_unit_ids": [],
    }
    svc = _execution_service(result={"change_set": _change_set(), "change_set_review_state": review_state})
    service = ChangeSetReviewService(execution_service=svc)

    response = await service.reject_units("exec-1", unit_ids=["unit-1"], actor_user_id="user-1")

    persisted_state = svc.patch_execution_result.await_args.kwargs["result_patch"][
        "change_set_review_state"
    ]
    assert persisted_state["accepted_unit_ids"] == []
    assert persisted_state["rejected_unit_ids"] == ["unit-1"]
    assert response["unit_states"][0]["state"] == "rejected"


@pytest.mark.asyncio
async def test_undo_marks_unit_undone() -> None:
    svc = _execution_service()
    service = ChangeSetReviewService(execution_service=svc)

    response = await service.undo_units("exec-1", unit_ids=["unit-2"], actor_user_id="user-1")

    persisted_state = svc.patch_execution_result.await_args.kwargs["result_patch"][
        "change_set_review_state"
    ]
    assert persisted_state["undone_unit_ids"] == ["unit-2"]
    assert response["unit_states"][1]["state"] == "undone"


@pytest.mark.asyncio
async def test_unknown_unit_id_raises_value_error() -> None:
    svc = _execution_service()
    service = ChangeSetReviewService(execution_service=svc)

    with pytest.raises(ValueError, match="unknown unit"):
        await service.accept_units("exec-1", unit_ids=["missing"], actor_user_id="user-1")


@pytest.mark.asyncio
async def test_blocked_units_can_be_explicitly_accepted_after_review() -> None:
    svc = _execution_service()
    service = ChangeSetReviewService(execution_service=svc)

    response = await service.accept_units(
        "exec-1",
        unit_ids=["unit-blocked"],
        actor_user_id="user-1",
    )

    persisted_state = svc.patch_execution_result.await_args.kwargs["result_patch"][
        "change_set_review_state"
    ]
    assert persisted_state["accepted_unit_ids"] == ["unit-blocked"]
    assert response["unit_states"][2]["state"] == "accepted"


@pytest.mark.asyncio
async def test_non_owner_is_hidden() -> None:
    svc = _execution_service(user_id="other-user")
    service = ChangeSetReviewService(execution_service=svc)

    with pytest.raises(ChangeSetReviewNotFoundError):
        await service.get_change_set("exec-1", actor_user_id="user-1")


@pytest.mark.asyncio
async def test_workspace_non_member_is_hidden() -> None:
    svc = _execution_service()
    dataservice = MagicMock()
    dataservice.workspace_has_active_membership = AsyncMock(return_value=False)
    service = ChangeSetReviewService(execution_service=svc, dataservice=dataservice)

    with pytest.raises(ChangeSetReviewNotFoundError):
        await service.get_change_set("exec-1", actor_user_id="user-1")


@pytest.mark.asyncio
async def test_persistence_failure_raises() -> None:
    svc = _execution_service(persisted_result={"change_set": _change_set()})
    service = ChangeSetReviewService(execution_service=svc)

    with pytest.raises(ChangeSetReviewPersistenceError):
        await service.accept_units("exec-1", unit_ids=["unit-1"], actor_user_id="user-1")
