"""One bounded MissionDriveSlice per Celery delivery."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from celery import shared_task

from src.mission_runtime import MissionReconciler, MissionRuntime
from src.mission_runtime.contracts import (
    MISSION_TASK_HARD_TIME_LIMIT_SECONDS,
    MISSION_TASK_SOFT_TIME_LIMIT_SECONDS,
)


def mission_worker_id(task_self: Any, mission_id: str) -> str:
    request = getattr(task_self, "request", None)
    request_id = str(getattr(request, "id", "") or "").strip()
    hostname = str(getattr(request, "hostname", "") or "mission-worker").strip()
    identity = f"{hostname}:{request_id or mission_id}"
    return identity[:160]


async def drive_mission_slice_async(
    mission_id: str,
    *,
    worker_id: str,
    command_hint: str | None = None,
    runtime: MissionRuntime | None = None,
) -> dict[str, Any]:
    if runtime is not None:
        result = await runtime.run_slice(
            mission_id,
            worker_id=worker_id,
            command_hint=command_hint,
        )
        return result.model_dump(mode="json")

    from src.dataservice_client.provider import dataservice_client
    from src.mission_runtime.composition import build_production_mission_runtime

    async with dataservice_client() as dataservice:
        configured_runtime = await build_production_mission_runtime(dataservice)
        result = await configured_runtime.run_slice(
            mission_id,
            worker_id=worker_id,
            command_hint=command_hint,
        )
        return result.model_dump(mode="json")


async def reconcile_missions_async(
    *,
    worker_id: str,
    limit: int = 20,
    runtime: MissionRuntime | None = None,
) -> dict[str, Any]:
    if runtime is None:
        from src.dataservice_client.provider import dataservice_client
        from src.mission_runtime.composition import build_production_mission_runtime

        async with dataservice_client() as dataservice:
            configured_runtime = await build_production_mission_runtime(dataservice)
            return await reconcile_missions_async(
                worker_id=worker_id,
                limit=limit,
                runtime=configured_runtime,
            )

    reconciler = MissionReconciler(
        store=runtime.store,
        wakeups=runtime.wakeups,
        events=runtime.events,
        clock=runtime.clock,
    )
    mission_ids = await reconciler.reconcile_once(worker_id=worker_id, limit=limit)
    return {"claimed": len(mission_ids), "mission_ids": mission_ids}


def _drive_mission_entry(
    task_self: Any,
    mission_id: str,
    command_hint: str | None = None,
) -> dict[str, Any]:
    from src.task.worker import run_worker_coroutine

    runner = cast(
        Callable[[Awaitable[dict[str, Any]]], dict[str, Any]],
        run_worker_coroutine,
    )
    return runner(
        drive_mission_slice_async(
            mission_id,
            worker_id=mission_worker_id(task_self, mission_id),
            command_hint=command_hint,
        )
    )


def _reconcile_missions_entry(
    task_self: Any,
    limit: int = 20,
) -> dict[str, Any]:
    from src.task.worker import run_worker_coroutine

    runner = cast(
        Callable[[Awaitable[dict[str, Any]]], dict[str, Any]],
        run_worker_coroutine,
    )
    return runner(
        reconcile_missions_async(
            worker_id=mission_worker_id(task_self, "reconciler"),
            limit=limit,
        )
    )


drive_mission = shared_task(
    bind=True,
    name="src.task.tasks.drive_mission",
    acks_late=True,
    reject_on_worker_lost=True,
    track_started=True,
    soft_time_limit=MISSION_TASK_SOFT_TIME_LIMIT_SECONDS,
    time_limit=MISSION_TASK_HARD_TIME_LIMIT_SECONDS,
)(_drive_mission_entry)

reconcile_missions = shared_task(
    bind=True,
    name="src.task.tasks.reconcile_missions",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=45,
    time_limit=60,
)(_reconcile_missions_entry)


__all__ = [
    "drive_mission",
    "drive_mission_slice_async",
    "mission_worker_id",
    "reconcile_missions",
    "reconcile_missions_async",
]
