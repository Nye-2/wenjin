"""Periodic retirement of expired Mission review previews."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, TypedDict, cast

from celery import shared_task

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.mission import MissionPreviewCleanupPayload
from src.review_commit_runtime.preview_store import MissionPreviewStore

MISSION_PREVIEW_CLEANUP_LIMIT = 200
MISSION_PREVIEW_CLEANUP_MAX_BATCHES = 5


class MissionPreviewCleanupSummary(TypedDict):
    review_projections_expired: int
    projection_refs_released: int
    projection_batches: int
    projection_drain_exhausted: bool
    preview_refs_deleted: int


async def cleanup_mission_previews_async(
    *,
    now: datetime | None = None,
    limit: int = MISSION_PREVIEW_CLEANUP_LIMIT,
    max_batches: int = MISSION_PREVIEW_CLEANUP_MAX_BATCHES,
    dataservice: AsyncDataServiceClient | None = None,
    preview_store: MissionPreviewStore | None = None,
) -> MissionPreviewCleanupSummary:
    """Retire DB projections before deleting their private preview files."""
    cutoff = now or datetime.now(UTC)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    else:
        cutoff = cutoff.astimezone(UTC)
    if not 1 <= limit <= 1000:
        raise ValueError("mission_preview_cleanup_limit_invalid")
    if not 1 <= max_batches <= MISSION_PREVIEW_CLEANUP_MAX_BATCHES:
        raise ValueError("mission_preview_cleanup_batch_count_invalid")

    if dataservice is None:
        from src.dataservice_client.provider import dataservice_client

        async with dataservice_client() as configured_dataservice:
            return await cleanup_mission_previews_async(
                now=cutoff,
                limit=limit,
                max_batches=max_batches,
                dataservice=configured_dataservice,
                preview_store=preview_store,
            )

    if preview_store is None:
        from src.review_commit_runtime.composition import get_mission_preview_store

        preview_store = get_mission_preview_store()

    expired_review_items = 0
    released_projection_refs = 0
    projection_batches = 0
    projection_drain_exhausted = False
    for _ in range(max_batches):
        projection_result = await dataservice.missions.cleanup_expired_previews(
            MissionPreviewCleanupPayload(now=cutoff, limit=limit)
        )
        projection_batches += 1
        expired_review_items += len(projection_result.review_item_ids)
        released_projection_refs += len(projection_result.preview_refs)
        if not projection_result.review_item_ids:
            projection_drain_exhausted = True
            break

    deleted_refs = (
        await preview_store.cleanup_expired(now=cutoff, limit=limit)
        if projection_drain_exhausted
        else []
    )
    return {
        "review_projections_expired": expired_review_items,
        "projection_refs_released": released_projection_refs,
        "projection_batches": projection_batches,
        "projection_drain_exhausted": projection_drain_exhausted,
        "preview_refs_deleted": len(deleted_refs),
    }


def _cleanup_mission_previews_entry(
    _task_self: Any,
    limit: int = MISSION_PREVIEW_CLEANUP_LIMIT,
) -> MissionPreviewCleanupSummary:
    from src.task.worker import run_worker_coroutine

    runner = cast(
        Callable[
            [Awaitable[MissionPreviewCleanupSummary]],
            MissionPreviewCleanupSummary,
        ],
        run_worker_coroutine,
    )
    return runner(cleanup_mission_previews_async(limit=limit))


cleanup_mission_previews = shared_task(
    bind=True,
    name="src.task.tasks.cleanup_mission_previews",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=45,
    time_limit=60,
)(_cleanup_mission_previews_entry)


__all__ = [
    "MISSION_PREVIEW_CLEANUP_LIMIT",
    "MISSION_PREVIEW_CLEANUP_MAX_BATCHES",
    "MissionPreviewCleanupSummary",
    "cleanup_mission_previews",
    "cleanup_mission_previews_async",
]
