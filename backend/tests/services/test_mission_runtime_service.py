from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

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
    runtime = SimpleNamespace(notify_runnable=AsyncMock(return_value=True))
    review_commit = SimpleNamespace(
        decide=AsyncMock(return_value=review_result),
        commit_many=AsyncMock(return_value=commit_result),
    )
    service = MissionRuntimeService(
        runtime,
        dataservice=SimpleNamespace(),
        review_commit=review_commit,
    )
    return service, runtime


@pytest.mark.asyncio
async def test_revision_review_publishes_delivery_hint() -> None:
    decision = ReviewDecision(
        review_item_id="review-1",
        action=ReviewAction.NEEDS_MORE_EVIDENCE,
    )
    service, runtime = _service(
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

    await service.decide_reviews(
        "mission-1",
        actor_user_id="user-1",
        decision_id="decision-1",
        decisions=[decision],
        bulk=False,
    )

    runtime.notify_runnable.assert_awaited_once_with(
        "mission-1",
        command_hint="decision-1",
    )


@pytest.mark.asyncio
async def test_successful_commit_publishes_delivery_hint() -> None:
    service, runtime = _service(
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

    runtime.notify_runnable.assert_awaited_once_with(
        "mission-1",
        command_hint="commit-1",
    )
