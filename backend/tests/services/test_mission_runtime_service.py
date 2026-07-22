from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.contracts.research_evidence import NON_BYPASSABLE_REVIEW_RISKS
from src.contracts.review_policy import ReviewMode
from src.dataservice_client.contracts.mission import MissionStatus
from src.review_commit_runtime.contracts import (
    CommitBatchOutcome,
    CommitOutcome,
    ReviewAction,
    ReviewDecision,
    ReviewDecisionBatchOutcome,
    ReviewDecisionOutcome,
)
from src.services.mission_runtime_service import MissionRuntimeService


def _service(*, review_result=None, commit_result=None):
    runtime = SimpleNamespace(
        start=AsyncMock(),
        notify_runnable=AsyncMock(return_value=True),
    )
    missions = SimpleNamespace(
        get=AsyncMock(),
        append_command=AsyncMock(),
        list_review_items=AsyncMock(return_value=[]),
        list_items=AsyncMock(return_value=[]),
        list_items_by_seqs=AsyncMock(return_value=[]),
    )
    review_commit = SimpleNamespace(
        decide=AsyncMock(return_value=review_result),
        commit_many=AsyncMock(return_value=commit_result),
    )
    service = MissionRuntimeService(
        runtime,
        dataservice=SimpleNamespace(missions=missions),
        review_commit=review_commit,
    )
    return service, runtime, missions


@pytest.mark.asyncio
async def test_nonterminal_review_feedback_appends_command_and_wakes_mission() -> None:
    decision = ReviewDecision(
        review_item_id="review-1",
        action=ReviewAction.NEEDS_MORE_EVIDENCE,
    )
    service, runtime, missions = _service(
        review_result=ReviewDecisionBatchOutcome(
            outcomes=[
                ReviewDecisionOutcome(
                    review_item_id="review-1",
                    action=decision.action,
                    applied=True,
                    status="needs_more_evidence",
                )
            ]
        )
    )
    missions.get.return_value = SimpleNamespace(
        mission_id="mission-1",
        user_id="user-1",
        status=MissionStatus.RUNNING,
        snapshot_json={
            "stage_acceptance": {
                "literature_positioning": {"result": "pass"},
            }
        },
    )
    missions.list_review_items.return_value = [SimpleNamespace(review_item_id="review-1", source_item_seq=9)]
    missions.list_items_by_seqs.return_value = [SimpleNamespace(seq=9, stage_id="literature_positioning")]

    result = await service.decide_reviews(
        "mission-1",
        actor_user_id="user-1",
        decision_id="decision-1",
        decisions=[decision],
    )

    command = missions.append_command.await_args.args[1]
    assert command.command_type == "review_feedback"
    assert command.payload_json["review_item_ids"] == ["review-1"]
    assert command.payload_json["reset_stage_ids"] == ["literature_positioning"]
    runtime.notify_runnable.assert_awaited_once()
    assert result.continuation_mission_id is None


def _pinned_policy_snapshot(*allowed_modes: ReviewMode) -> dict[str, object]:
    return {
        "review_policy": {
            "default_mode": ReviewMode.BALANCED_DEFAULT.value,
            "allowed_modes": [mode.value for mode in allowed_modes],
            "non_bypassable_risks": sorted(NON_BYPASSABLE_REVIEW_RISKS),
        }
    }


@pytest.mark.asyncio
async def test_set_review_mode_accepts_only_a_mode_allowed_by_pinned_policy() -> None:
    service, runtime, missions = _service()
    missions.get.return_value = SimpleNamespace(
        user_id="user-1",
        status=MissionStatus.RUNNING,
        runtime_context_json={
            "mission_policy_snapshot": _pinned_policy_snapshot(
                ReviewMode.BALANCED_DEFAULT,
                ReviewMode.REVIEW_ALL,
            )
        },
    )
    missions.append_command.return_value = SimpleNamespace(mission=missions.get.return_value)

    await service.set_review_mode(
        "mission-1",
        command_id="review-mode-1",
        actor_user_id="user-1",
        review_mode=ReviewMode.REVIEW_ALL,
    )

    missions.append_command.assert_awaited_once()
    runtime.notify_runnable.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_review_mode_rejects_mode_outside_pinned_policy() -> None:
    service, runtime, missions = _service()
    missions.get.return_value = SimpleNamespace(
        user_id="user-1",
        status=MissionStatus.RUNNING,
        runtime_context_json={
            "mission_policy_snapshot": _pinned_policy_snapshot(
                ReviewMode.BALANCED_DEFAULT,
            )
        },
    )

    with pytest.raises(ValueError, match="not allowed by the pinned MissionPolicy"):
        await service.set_review_mode(
            "mission-1",
            command_id="review-mode-1",
            actor_user_id="user-1",
            review_mode=ReviewMode.AUTO_DRAFT,
        )

    missions.append_command.assert_not_awaited()
    runtime.notify_runnable.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_commit_does_not_reopen_research_loop() -> None:
    service, runtime, missions = _service(
        commit_result=CommitBatchOutcome(
            outcomes=[
                CommitOutcome(
                    review_item_id="review-1",
                    committed=True,
                )
            ]
        )
    )

    await service.commit_reviews(
        "mission-1",
        actor_user_id="user-1",
        review_item_ids=("review-1",),
        request_id="commit-1",
    )

    runtime.notify_runnable.assert_not_awaited()
    runtime.start.assert_not_awaited()
    missions.append_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_terminal_review_feedback_starts_stage_scoped_child_mission() -> None:
    decision = ReviewDecision(
        review_item_id="review-1",
        action=ReviewAction.NEEDS_MORE_EVIDENCE,
        rationale="补充近两年的对照工作",
    )
    service, runtime, missions = _service(
        review_result=ReviewDecisionBatchOutcome(
            outcomes=[
                ReviewDecisionOutcome(
                    review_item_id="review-1",
                    action=decision.action,
                    applied=True,
                    status="needs_more_evidence",
                )
            ]
        )
    )
    parent = SimpleNamespace(
        mission_id="mission-1",
        workspace_id="workspace-1",
        thread_id="thread-1",
        user_id="user-1",
        workspace_type="sci",
        mission_policy_id="sci_research",
        title="研究空白",
        objective="形成研究空白与创新点",
        status=MissionStatus.COMPLETED,
        review_mode="balanced_default",
        model_id="gpt-5.6-terra",
        reasoning_effort="xhigh",
        snapshot_json={
            "stage_acceptance": {
                "scope_topic": {"result": "pass"},
                "literature_positioning": {"result": "pass"},
            }
        },
        runtime_context_json={
            "policy_content_hash": "a" * 64,
            "model_capability_profile_hash": "b" * 64,
        },
    )
    missions.get.return_value = parent
    missions.list_review_items.return_value = [SimpleNamespace(review_item_id="review-1", source_item_seq=9)]
    missions.list_items_by_seqs.return_value = [SimpleNamespace(seq=9, stage_id="literature_positioning")]
    runtime.start.return_value = SimpleNamespace(mission_id="mission-child-1")

    result = await service.decide_reviews(
        "mission-1",
        actor_user_id="user-1",
        decision_id="decision-terminal-1",
        decisions=[decision],
    )

    request = runtime.start.await_args.args[0]
    assert request.parent_mission_id == "mission-1"
    assert request.continuation.reset_stage_ids == ("literature_positioning",)
    assert request.continuation.review_item_ids == ("review-1",)
    assert result.continuation_mission_id == "mission-child-1"


@pytest.mark.asyncio
async def test_terminal_review_feedback_never_guesses_a_missing_source_stage() -> None:
    decision = ReviewDecision(
        review_item_id="review-1",
        action=ReviewAction.NEEDS_MORE_EVIDENCE,
    )
    service, runtime, missions = _service(
        review_result=ReviewDecisionBatchOutcome(
            outcomes=[
                ReviewDecisionOutcome(
                    review_item_id="review-1",
                    action=decision.action,
                    applied=True,
                    status="needs_more_evidence",
                )
            ]
        )
    )
    missions.get.return_value = SimpleNamespace(
        mission_id="mission-1",
        user_id="user-1",
        status=MissionStatus.COMPLETED,
        snapshot_json={
            "stage_acceptance": {
                "literature_positioning": {"result": "pass"},
            }
        },
    )
    missions.list_review_items.return_value = [SimpleNamespace(review_item_id="review-1", source_item_seq=None)]

    result = await service.decide_reviews(
        "mission-1",
        actor_user_id="user-1",
        decision_id="decision-missing-source",
        decisions=[decision],
    )

    assert result.continuation_mission_id is None
    assert result.continuation_error_code == "review_source_stage_unavailable"
    runtime.start.assert_not_awaited()
    missions.list_items_by_seqs.assert_not_awaited()
