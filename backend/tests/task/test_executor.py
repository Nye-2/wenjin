"""Tests for task executor abstraction."""

from unittest.mock import MagicMock, patch

import pytest


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
        import src.task.executor as executor_module
        from src.task.executor import CeleryExecutor, get_executor

        with patch("src.task.executor.celery_settings") as mock_settings:
            mock_settings.enabled = True
            executor_module._CELERY_EXECUTOR = None
            executor = get_executor()
            assert isinstance(executor, CeleryExecutor)

    def test_raises_when_celery_disabled(self):
        from src.task.executor import get_executor

        with patch("src.task.executor.celery_settings") as mock_settings:
            mock_settings.enabled = False
            with pytest.raises(RuntimeError, match="CELERY_ENABLED=true"):
                get_executor()

    def test_returns_same_celery_instance(self):
        import src.task.executor as executor_module
        from src.task.executor import get_executor

        with patch("src.task.executor.celery_settings") as mock_settings:
            mock_settings.enabled = True
            executor_module._CELERY_EXECUTOR = None
            first = get_executor()
            second = get_executor()
        assert first is second
