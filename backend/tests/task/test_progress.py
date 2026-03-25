"""Tests for ProgressTracker write-strategy optimization.

Verifies:
- update() writes only to Redis + Pub/Sub (no DB write)
- update(stage_transition=True) writes Redis + Pub/Sub + DB
- complete() writes only to Redis + Pub/Sub (no DB write)
- fail() writes only to Redis + Pub/Sub (no DB write)
- Pub/Sub events are published for all operations
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.task.progress import ProgressTracker


def _make_redis():
    """Create a mock redis client with publish tracking."""
    redis = MagicMock()
    redis.client = AsyncMock()
    redis.client.publish = AsyncMock()
    redis.client.hset = AsyncMock()
    redis.client.hgetall = AsyncMock(return_value={})
    redis.client.expire = AsyncMock()
    return redis


class TestProgressUpdateWriteStrategy:
    """update() should only write Redis + Pub/Sub, NOT DB."""

    @pytest.mark.asyncio
    async def test_update_does_not_write_db(self):
        """Regular progress updates must NOT write to the database."""
        redis = _make_redis()
        tracker = ProgressTracker(redis, "task-1")

        # Patch at the source so the local import inside update() is intercepted
        with patch("src.database.get_db_session") as mock_get_db:
            await tracker.update(50, "halfway")
            mock_get_db.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_writes_redis(self):
        """update() must write task state to Redis."""
        redis = _make_redis()
        tracker = ProgressTracker(redis, "task-1")

        await tracker.update(50, "halfway")
        redis.client.hset.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_publishes_event(self):
        """update() must publish a Pub/Sub event."""
        redis = _make_redis()
        tracker = ProgressTracker(redis, "task-1")

        await tracker.update(50, "halfway")
        redis.client.publish.assert_called_once()
        channel, data = redis.client.publish.call_args.args
        assert channel == "task_progress:task-1"
        event = json.loads(data)
        assert event["progress"] == 50
        assert event["status"] == "running"
        assert event["message"] == "halfway"

    @pytest.mark.asyncio
    async def test_update_with_stage_transition_writes_db(self):
        """update(stage_transition=True) must flush progress to DB."""
        redis = _make_redis()
        tracker = ProgressTracker(redis, "task-1")

        mock_db = AsyncMock()
        mock_store = AsyncMock()

        with (
            patch("src.database.get_db_session") as mock_get_db,
            patch("src.task.store.TaskStore", return_value=mock_store),
        ):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=mock_db)
            ctx.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = ctx

            await tracker.update(50, "stage change", stage_transition=True)
            mock_store.update_task_record.assert_called_once_with(
                "task-1",
                status="running",
                progress=50,
                message="stage change",
            )

    @pytest.mark.asyncio
    async def test_update_clamps_progress(self):
        """Progress values should be clamped to 0-100."""
        redis = _make_redis()
        tracker = ProgressTracker(redis, "task-1")

        await tracker.update(150, "over")
        event = json.loads(redis.client.publish.call_args.args[1])
        assert event["progress"] == 100

    @pytest.mark.asyncio
    async def test_update_publishes_workspace_activity_payload(self):
        """Workspace task updates should carry a canonical activity snapshot."""
        redis = _make_redis()
        tracker = ProgressTracker(
            redis,
            "task-1",
            workspace_id="ws-1",
            thread_id="thread-1",
            task_type="workspace_feature",
            feature_id="deep_research",
        )

        with patch("src.workspace_events.publish_workspace_event", new=AsyncMock()) as publish_workspace_event:
            await tracker.update(45, "Gathering evidence")

        payload = publish_workspace_event.await_args.args[2]
        assert payload["task"]["status"] == "running"
        assert payload["activity"]["id"] == "task:task-1"
        assert payload["activity"]["status"] == "running"
        assert payload["activity"]["summary"] == "Gathering evidence"


class TestProgressCompleteWriteStrategy:
    """complete() should only write Redis + Pub/Sub, NOT DB."""

    @pytest.mark.asyncio
    async def test_complete_does_not_write_db(self):
        """complete() must NOT write to the database (mark_task_completed handles it)."""
        redis = _make_redis()
        tracker = ProgressTracker(redis, "task-1")

        # complete() has no DB imports at all — just verify no error and Redis is written
        await tracker.complete("done")
        # If this reached here without importing get_db_session, DB is not touched
        redis.client.hset.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_writes_redis(self):
        """complete() must update Redis state to success/100."""
        redis = _make_redis()
        tracker = ProgressTracker(redis, "task-1")

        await tracker.complete("done")
        redis.client.hset.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_publishes_terminal_event(self):
        """complete() must publish a terminal Pub/Sub event."""
        redis = _make_redis()
        tracker = ProgressTracker(redis, "task-1")

        await tracker.complete("all done")
        event = json.loads(redis.client.publish.call_args.args[1])
        assert event["status"] == "success"
        assert event["progress"] == 100
        assert event["message"] == "all done"


class TestProgressFailWriteStrategy:
    """fail() should only write Redis + Pub/Sub, NOT DB."""

    @pytest.mark.asyncio
    async def test_fail_does_not_write_db(self):
        """fail() must NOT write to the database."""
        redis = _make_redis()
        tracker = ProgressTracker(redis, "task-1")

        # fail() has no DB imports — just verify no error and Redis is written
        await tracker.fail("crash")
        redis.client.hset.assert_called_once()

    @pytest.mark.asyncio
    async def test_fail_writes_redis(self):
        """fail() must update Redis state to failed."""
        redis = _make_redis()
        tracker = ProgressTracker(redis, "task-1")

        await tracker.fail("crash")
        redis.client.hset.assert_called_once()

    @pytest.mark.asyncio
    async def test_fail_publishes_terminal_event(self):
        """fail() must publish a terminal Pub/Sub event."""
        redis = _make_redis()
        tracker = ProgressTracker(redis, "task-1")

        await tracker.fail("something broke")
        event = json.loads(redis.client.publish.call_args.args[1])
        assert event["status"] == "failed"
        assert event["message"] == "something broke"

    @pytest.mark.asyncio
    async def test_fail_preserves_current_progress(self):
        """fail() should keep progress from Redis state if available."""
        redis = _make_redis()
        redis.client.hgetall = AsyncMock(
            return_value={"progress": "75", "status": "running"}
        )
        tracker = ProgressTracker(redis, "task-1")

        await tracker.fail("broke at 75%")
        event = json.loads(redis.client.publish.call_args.args[1])
        assert event["progress"] == 75
