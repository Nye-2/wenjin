from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mission_runtime.contracts import (
    MISSION_BROKER_VISIBILITY_TIMEOUT_SECONDS,
    MISSION_SLICE_SHUTDOWN_MARGIN_SECONDS,
    MISSION_SLICE_WALL_TIME_SECONDS,
    MISSION_SUBAGENT_OPERATION_TIME_SECONDS,
    MISSION_TASK_HARD_TIME_LIMIT_SECONDS,
    MISSION_TASK_SOFT_TIME_LIMIT_SECONDS,
    MISSION_WORKER_PREFETCH_MULTIPLIER,
)
from src.services.mission_runtime_service import CeleryMissionWakeupPublisher
from src.task.celery_app import celery_app
from src.task.tasks.mission import (
    drive_mission,
    drive_mission_slice_async,
    mission_worker_id,
    reconcile_missions,
)


def test_mission_task_has_bounded_long_running_delivery_profile() -> None:
    assert drive_mission.name == "src.task.tasks.drive_mission"
    assert drive_mission.acks_late is True
    assert drive_mission.reject_on_worker_lost is True
    assert drive_mission.soft_time_limit == MISSION_TASK_SOFT_TIME_LIMIT_SECONDS
    assert drive_mission.time_limit == MISSION_TASK_HARD_TIME_LIMIT_SECONDS
    assert celery_app.conf.task_routes[drive_mission.name]["queue"] == "long_running"
    assert celery_app.conf.task_routes[reconcile_missions.name]["queue"] == "default"
    assert celery_app.conf.beat_schedule["reconcile-runnable-missions"]["task"] == reconcile_missions.name
    assert MISSION_WORKER_PREFETCH_MULTIPLIER == 1
    assert (
        MISSION_SLICE_WALL_TIME_SECONDS
        + MISSION_SUBAGENT_OPERATION_TIME_SECONDS
        + MISSION_SLICE_SHUTDOWN_MARGIN_SECONDS
        < MISSION_TASK_SOFT_TIME_LIMIT_SECONDS
        < MISSION_TASK_HARD_TIME_LIMIT_SECONDS
        < MISSION_BROKER_VISIBILITY_TIMEOUT_SECONDS
    )
    assert celery_app.conf.broker_transport_options["visibility_timeout"] == MISSION_BROKER_VISIBILITY_TIMEOUT_SECONDS


def test_mission_worker_id_uses_delivery_identity() -> None:
    task = SimpleNamespace(request=SimpleNamespace(id="delivery-17", hostname="mission-worker-a"))
    assert mission_worker_id(task, "mission-1") == "mission-worker-a:delivery-17"


@pytest.mark.asyncio
async def test_drive_slice_returns_only_runtime_telemetry() -> None:
    telemetry = SimpleNamespace(
        model_dump=lambda **_kwargs: {
            "mission_id": "mission-1",
            "outcome": "yielded",
            "status": "running",
            "reason": "slice_budget_exhausted",
        }
    )
    runtime = SimpleNamespace(run_slice=AsyncMock(return_value=telemetry))
    result = await drive_mission_slice_async(
        "mission-1",
        worker_id="worker-1",
        command_hint="command-1",
        runtime=runtime,
    )

    runtime.run_slice.assert_awaited_once_with(
        "mission-1",
        worker_id="worker-1",
        command_hint="command-1",
    )
    assert result == {
        "mission_id": "mission-1",
        "outcome": "yielded",
        "status": "running",
        "reason": "slice_budget_exhausted",
    }


@pytest.mark.asyncio
async def test_drive_slice_builds_production_runtime_without_manual_bootstrap() -> None:
    telemetry = SimpleNamespace(
        model_dump=lambda **_kwargs: {
            "mission_id": "mission-1",
            "outcome": "completed",
            "status": "completed",
            "reason": "mission_completed",
        }
    )
    runtime = SimpleNamespace(run_slice=AsyncMock(return_value=telemetry))
    review_commit = SimpleNamespace(
        reconcile_auto_drafts=AsyncMock(
            return_value=SimpleNamespace(outcomes=[])
        )
    )
    dataservice = SimpleNamespace(name="dataservice")

    @asynccontextmanager
    async def client_context():
        yield dataservice

    with (
        patch(
            "src.dataservice_client.provider.dataservice_client",
            return_value=client_context(),
        ),
        patch(
            "src.mission_runtime.composition.build_production_mission_runtime",
            new=AsyncMock(return_value=runtime),
        ) as builder,
        patch(
            "src.review_commit_runtime.composition.build_review_commit_runtime",
            return_value=review_commit,
        ) as review_builder,
    ):
        result = await drive_mission_slice_async(
            "mission-1",
            worker_id="worker-1",
        )

    builder.assert_awaited_once_with(dataservice)
    review_builder.assert_called_once_with(dataservice)
    assert review_commit.reconcile_auto_drafts.await_count == 2
    runtime.run_slice.assert_awaited_once_with(
        "mission-1",
        worker_id="worker-1",
        command_hint=None,
    )
    assert result["outcome"] == "completed"


@pytest.mark.asyncio
async def test_celery_wakeup_payload_contains_only_mission_and_optional_hint() -> None:
    publisher = CeleryMissionWakeupPublisher()
    fake_app = MagicMock()

    with patch("src.task.celery_app.celery_app", fake_app):
        await publisher.publish("mission-1", command_hint="command-1")

    fake_app.send_task.assert_called_once_with(
        "src.task.tasks.drive_mission",
        args=["mission-1"],
        kwargs={"command_hint": "command-1"},
        queue="long_running",
    )
