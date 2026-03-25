"""Tests for task executor abstraction."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_redis_client():
    client = AsyncMock()
    client.client = AsyncMock()
    client.client.hset = AsyncMock()
    client.client.expire = AsyncMock()
    client.client.publish = AsyncMock()
    client.client.hgetall = AsyncMock(return_value={})
    client._client = True  # pretend connected
    return client


class TestLocalExecutor:
    """Tests for in-process task execution when Celery is disabled."""

    @pytest.mark.asyncio
    async def test_execute_runs_task_in_background(self, mock_redis_client):
        """LocalExecutor should schedule task via asyncio.create_task."""
        from src.task.executor import LocalExecutor

        executor = LocalExecutor(max_concurrency=2)

        with patch("src.task.executor._run_task_locally", new_callable=AsyncMock) as mock_run:
            await executor.execute(
                task_id="test-task-1",
                task_type="workspace_feature",
                payload={"workspace_id": "ws-1"},
                queue="default",
            )
            # Give the background task a chance to start
            await asyncio.sleep(0.05)
            mock_run.assert_called_once_with("test-task-1", "workspace_feature", {"workspace_id": "ws-1"})

    @pytest.mark.asyncio
    async def test_execute_respects_semaphore(self):
        """LocalExecutor should limit concurrent executions."""
        from src.task.executor import LocalExecutor

        executor = LocalExecutor(max_concurrency=1)
        started = asyncio.Event()
        blocker = asyncio.Event()

        async def slow_task(task_id, task_type, payload):
            started.set()
            await blocker.wait()

        with patch("src.task.executor._run_task_locally", side_effect=slow_task):
            # Start first task — should acquire semaphore
            await executor.execute("t1", "workspace_feature", {}, "default")
            await started.wait()

            # Start second task — should be queued (not started yet)
            second_started = False

            async def mark_second(task_id, task_type, payload):
                nonlocal second_started
                second_started = True

            with patch("src.task.executor._run_task_locally", side_effect=mark_second):
                await executor.execute("t2", "workspace_feature", {}, "default")
                await asyncio.sleep(0.05)
                assert not second_started, "Second task should be blocked by semaphore"

            # Release first task
            blocker.set()
            await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_run_task_locally_reuses_shared_task_flow() -> None:
    """Local execution should delegate to the shared task runner used by Celery."""
    with patch("src.task.tasks.base._execute_task_async", new_callable=AsyncMock) as mock_execute:
        from src.task.executor import _run_task_locally

        await _run_task_locally("task-1", "workspace_feature", {"workspace_id": "ws-1"})

    mock_execute.assert_awaited_once()
    local_task = mock_execute.await_args.args[0]
    assert local_task.request.hostname == "local-executor"
    assert mock_execute.await_args.args[1:] == (
        "task-1",
        "workspace_feature",
        {"workspace_id": "ws-1"},
    )


class TestCeleryExecutor:
    """Tests for Celery-based task execution."""

    @pytest.mark.asyncio
    async def test_execute_sends_to_celery(self):
        """CeleryExecutor should call celery_app.send_task."""
        from src.task.executor import CeleryExecutor

        mock_celery = MagicMock()
        executor = CeleryExecutor(celery_app=mock_celery)

        await executor.execute(
            task_id="test-task-1",
            task_type="workspace_feature",
            payload={"workspace_id": "ws-1"},
            queue="default",
        )

        mock_celery.send_task.assert_called_once_with(
            "src.task.tasks.execute_task",
            args=["test-task-1", "workspace_feature", {"workspace_id": "ws-1"}],
            queue="default",
            priority=5,
            task_id="test-task-1",
        )


class TestGetExecutor:
    """Tests for executor factory function."""

    def test_returns_celery_when_enabled(self):
        from src.task.executor import CeleryExecutor, get_executor

        with patch("src.task.executor.celery_settings") as mock_settings:
            mock_settings.enabled = True
            executor = get_executor()
            assert isinstance(executor, CeleryExecutor)

    def test_returns_local_when_disabled(self):
        from src.task.executor import LocalExecutor, get_executor

        with patch("src.task.executor.celery_settings") as mock_settings:
            mock_settings.enabled = False
            executor = get_executor()
            assert isinstance(executor, LocalExecutor)

    def test_returns_same_local_instance_when_disabled(self):
        """Local executor should be process-scoped so semaphore is effective."""
        import src.task.executor as executor_module

        with patch("src.task.executor.celery_settings") as mock_settings:
            mock_settings.enabled = False
            # Reset singleton cache for deterministic test
            executor_module._LOCAL_EXECUTOR = None

            first = executor_module.get_executor()
            second = executor_module.get_executor()

            assert first is second
