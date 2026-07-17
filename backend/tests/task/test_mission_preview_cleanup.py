from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.dataservice_client.contracts.mission import MissionPreviewCleanupPayload
from src.task.celery_app import (
    MISSION_PREVIEW_CLEANUP_INTERVAL_SECONDS,
    celery_app,
)
from src.task.tasks.mission_preview_cleanup import (
    MISSION_PREVIEW_CLEANUP_LIMIT,
    MISSION_PREVIEW_CLEANUP_MAX_BATCHES,
    cleanup_mission_previews,
    cleanup_mission_previews_async,
)


@pytest.mark.asyncio
async def test_cleanup_retires_projection_before_files_with_same_cutoff() -> None:
    cutoff = datetime(2026, 7, 17, 3, 4, tzinfo=UTC)
    calls: list[str] = []
    projection_calls = 0

    async def cleanup_projection(command: MissionPreviewCleanupPayload):
        nonlocal projection_calls
        projection_calls += 1
        calls.append("projection")
        assert command == MissionPreviewCleanupPayload(
            now=cutoff,
            limit=MISSION_PREVIEW_CLEANUP_LIMIT,
        )
        if projection_calls == 1:
            return SimpleNamespace(
                review_item_ids=["review-1", "review-2"],
                preview_refs=["preview-1"],
            )
        return SimpleNamespace(review_item_ids=[], preview_refs=[])

    async def cleanup_files(*, now: datetime, limit: int):
        calls.append("files")
        assert now == cutoff
        assert limit == MISSION_PREVIEW_CLEANUP_LIMIT
        return ["preview-1"]

    dataservice = SimpleNamespace(
        missions=SimpleNamespace(cleanup_expired_previews=cleanup_projection)
    )
    preview_store = SimpleNamespace(cleanup_expired=cleanup_files)

    result = await cleanup_mission_previews_async(
        now=cutoff,
        dataservice=dataservice,
        preview_store=preview_store,
    )

    assert calls == ["projection", "projection", "files"]
    assert result == {
        "review_projections_expired": 2,
        "projection_refs_released": 1,
        "projection_batches": 2,
        "projection_drain_exhausted": True,
        "preview_refs_deleted": 1,
    }


@pytest.mark.asyncio
async def test_projection_failure_does_not_start_file_cleanup() -> None:
    error = RuntimeError("dataservice unavailable")
    dataservice = SimpleNamespace(
        missions=SimpleNamespace(
            cleanup_expired_previews=AsyncMock(side_effect=error)
        )
    )
    preview_store = SimpleNamespace(cleanup_expired=AsyncMock())

    with pytest.raises(RuntimeError, match="dataservice unavailable"):
        await cleanup_mission_previews_async(
            dataservice=dataservice,
            preview_store=preview_store,
        )

    preview_store.cleanup_expired.assert_not_awaited()


@pytest.mark.asyncio
async def test_file_failure_is_reported_after_projection_commit() -> None:
    cleanup_projection = AsyncMock(
        side_effect=[
            SimpleNamespace(review_item_ids=["review-1"], preview_refs=["preview-1"]),
            SimpleNamespace(review_item_ids=[], preview_refs=[]),
        ]
    )
    dataservice = SimpleNamespace(
        missions=SimpleNamespace(cleanup_expired_previews=cleanup_projection)
    )
    preview_store = SimpleNamespace(
        cleanup_expired=AsyncMock(side_effect=OSError("preview volume unavailable"))
    )

    with pytest.raises(OSError, match="preview volume unavailable"):
        await cleanup_mission_previews_async(
            dataservice=dataservice,
            preview_store=preview_store,
        )

    assert cleanup_projection.await_count == 2
    preview_store.cleanup_expired.assert_awaited_once()


@pytest.mark.asyncio
async def test_backlog_larger_than_drain_budget_keeps_all_preview_files(tmp_path) -> None:
    from src.review_commit_runtime.preview_store import MissionPreviewStore

    cutoff = datetime.now(UTC)
    store = MissionPreviewStore(
        tmp_path,
        default_ttl_seconds=3600,
        max_bytes=1024 * 1024,
    )
    descriptor = await store.put(
        workspace_id="workspace-1",
        content=(
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b"<text>still referenced</text></svg>"
        ),
        mime_type="image/svg+xml",
        filename="preview.svg",
        expires_at=cutoff + timedelta(seconds=1),
    )
    full_batch = SimpleNamespace(
        review_item_ids=[f"review-{index}" for index in range(MISSION_PREVIEW_CLEANUP_LIMIT)],
        preview_refs=[],
    )
    cleanup_projection = AsyncMock(return_value=full_batch)
    dataservice = SimpleNamespace(
        missions=SimpleNamespace(cleanup_expired_previews=cleanup_projection)
    )

    result = await cleanup_mission_previews_async(
        now=cutoff + timedelta(minutes=1),
        dataservice=dataservice,
        preview_store=store,
    )

    assert cleanup_projection.await_count == MISSION_PREVIEW_CLEANUP_MAX_BATCHES
    assert result["projection_drain_exhausted"] is False
    assert result["preview_refs_deleted"] == 0
    preview = await store.read(descriptor.ref, workspace_id="workspace-1")
    assert b"still referenced" in preview.content


def test_cleanup_task_is_bounded_retryable_and_periodic() -> None:
    task_name = "src.task.tasks.cleanup_mission_previews"

    assert cleanup_mission_previews.name == task_name
    assert cleanup_mission_previews.acks_late is True
    assert cleanup_mission_previews.reject_on_worker_lost is True
    assert cleanup_mission_previews.autoretry_for == (Exception,)
    assert cleanup_mission_previews.retry_backoff is True
    assert cleanup_mission_previews.retry_jitter is True
    assert cleanup_mission_previews.max_retries == 3
    assert task_name in celery_app.tasks
    assert celery_app.conf.task_routes[task_name]["queue"] == "default"
    assert celery_app.conf.beat_schedule["cleanup-expired-mission-previews"] == {
        "task": task_name,
        "schedule": MISSION_PREVIEW_CLEANUP_INTERVAL_SECONDS,
    }
    assert sum(
        entry["task"] == task_name
        for entry in celery_app.conf.beat_schedule.values()
    ) == 1


@pytest.mark.asyncio
async def test_cleanup_rejects_unbounded_limit_before_side_effects() -> None:
    dataservice = SimpleNamespace(
        missions=SimpleNamespace(cleanup_expired_previews=AsyncMock())
    )
    preview_store = SimpleNamespace(cleanup_expired=AsyncMock())

    with pytest.raises(ValueError, match="mission_preview_cleanup_limit_invalid"):
        await cleanup_mission_previews_async(
            limit=1001,
            dataservice=dataservice,
            preview_store=preview_store,
        )

    dataservice.missions.cleanup_expired_previews.assert_not_awaited()
    preview_store.cleanup_expired.assert_not_awaited()
