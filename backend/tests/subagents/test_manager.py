"""Tests for GlobalSubagentManager and ThreadContext."""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from src.subagents.manager import ThreadContext, GlobalSubagentManager
from src.subagents.models import SubagentTask, SubagentResult, SubagentStatus


class TestThreadContext:
    def test_create_context(self):
        ctx = ThreadContext(thread_id="thread-1", max_concurrent=3)
        assert ctx.thread_id == "thread-1"
        assert ctx.total_tasks == 0

    def test_store_and_get_result(self):
        ctx = ThreadContext(thread_id="thread-1", max_concurrent=3)
        result = SubagentResult(
            task_id="task-1",
            status=SubagentStatus.COMPLETED,
            output="Done",
            error=None
        )
        ctx.store_result("task-1", result)
        assert ctx.get_result("task-1") is result

    def test_get_result_nonexistent(self):
        ctx = ThreadContext(thread_id="thread-1", max_concurrent=3)
        assert ctx.get_result("nonexistent") is None

    def test_get_task_status_from_result(self):
        ctx = ThreadContext(thread_id="thread-1", max_concurrent=3)
        result = SubagentResult(
            task_id="task-1",
            status=SubagentStatus.FAILED,
            output=None,
            error="Error occurred"
        )
        ctx.store_result("task-1", result)
        assert ctx.get_task_status("task-1") == SubagentStatus.FAILED

    def test_get_task_status_running(self):
        ctx = ThreadContext(thread_id="thread-1", max_concurrent=3)
        # Create a mock task that's not done
        mock_task = MagicMock()
        mock_task.done.return_value = False
        ctx._tasks["task-1"] = mock_task
        assert ctx.get_task_status("task-1") == SubagentStatus.RUNNING

    def test_get_task_status_nonexistent(self):
        ctx = ThreadContext(thread_id="thread-1", max_concurrent=3)
        assert ctx.get_task_status("nonexistent") is None


class TestGlobalSubagentManager:
    @pytest.fixture
    def manager(self, subagent_config):
        GlobalSubagentManager.reset()
        manager = GlobalSubagentManager(subagent_config)
        GlobalSubagentManager._instance = manager
        yield manager
        GlobalSubagentManager.reset()

    def test_singleton(self, subagent_config):
        GlobalSubagentManager.reset()
        m1 = GlobalSubagentManager.initialize(subagent_config)
        m2 = GlobalSubagentManager.get_instance()
        assert m1 is m2
        GlobalSubagentManager.reset()

    def test_initialize_already_initialized(self, subagent_config):
        GlobalSubagentManager.reset()
        GlobalSubagentManager.initialize(subagent_config)
        with pytest.raises(RuntimeError, match="already initialized"):
            GlobalSubagentManager.initialize(subagent_config)
        GlobalSubagentManager.reset()

    def test_get_instance_not_initialized(self):
        GlobalSubagentManager.reset()
        with pytest.raises(RuntimeError, match="not initialized"):
            GlobalSubagentManager.get_instance()

    @pytest.mark.asyncio
    async def test_spawn_task(self, manager):
        """Test spawning a task."""
        task = SubagentTask(
            task_id="task-123",
            thread_id="thread-456",
            prompt="Test",
            created_at=datetime.now(),
            timeout=60,
        )

        # Mock the graph creation and invocation
        from unittest.mock import patch, MagicMock

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="Done")]
        })

        with patch.object(manager._graph_registry, 'get', return_value=None), \
             patch('src.subagents.manager.create_default_subagent_graph', return_value=mock_graph):

            task_id = await manager.spawn(task)
            assert task_id == "task-123"

            # Wait for task to complete
            await asyncio.sleep(0.2)
            status = await manager.get_status("thread-456", "task-123")
            assert status == SubagentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cancel_task(self, manager):
        """Test cancelling a task."""
        task = SubagentTask(
            task_id="cancel-test",
            thread_id="thread-cancel",
            prompt="Test",
            created_at=datetime.now(),
            timeout=60,
        )

        from unittest.mock import patch, MagicMock

        # Create a mock graph that will hang
        async def slow_invoke(*args, **kwargs):
            await asyncio.sleep(10)
            return {"messages": []}

        mock_graph = MagicMock()
        mock_graph.ainvoke = slow_invoke

        with patch.object(manager._graph_registry, 'get', return_value=mock_graph):
            await manager.spawn(task)
            await asyncio.sleep(0.05)

            success = await manager.cancel("thread-cancel", "cancel-test")
            assert success is True

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task(self, manager):
        success = await manager.cancel("thread-x", "task-x")
        assert success is False

    @pytest.mark.asyncio
    async def test_get_status_nonexistent_thread(self, manager):
        status = await manager.get_status("nonexistent", "task-x")
        assert status is None

    @pytest.mark.asyncio
    async def test_get_result(self, manager):
        """Test getting task result."""
        task = SubagentTask(
            task_id="result-test",
            thread_id="thread-result",
            prompt="Test",
            created_at=datetime.now(),
            timeout=60,
        )

        from unittest.mock import patch, MagicMock

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="Success")]
        })

        with patch.object(manager._graph_registry, 'get', return_value=mock_graph):
            await manager.spawn(task)
            await asyncio.sleep(0.1)

            result = await manager.get_result("thread-result", "result-test")
            assert result is not None
            assert result.status == SubagentStatus.COMPLETED
            assert result.output == "Success"

    @pytest.mark.asyncio
    async def test_get_result_nonexistent(self, manager):
        result = await manager.get_result("nonexistent", "task-x")
        assert result is None

    @pytest.mark.asyncio
    async def test_cleanup_thread(self, manager):
        """Test cleaning up a thread."""
        task = SubagentTask(
            task_id="cleanup-test",
            thread_id="thread-cleanup",
            prompt="Test",
            created_at=datetime.now(),
            timeout=60,
        )

        from unittest.mock import patch, MagicMock

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="Done")]
        })

        with patch.object(manager._graph_registry, 'get', return_value=mock_graph):
            await manager.spawn(task)
            await asyncio.sleep(0.1)

            assert "thread-cleanup" in manager._threads
            await manager.cleanup_thread("thread-cleanup")
            assert "thread-cleanup" not in manager._threads

    @pytest.mark.asyncio
    async def test_cleanup_nonexistent_thread(self, manager):
        # Should not raise
        await manager.cleanup_thread("nonexistent")

    @pytest.mark.asyncio
    async def test_concurrent_spawn_multiple_threads(self, manager):
        """Test spawning tasks across multiple threads."""
        from unittest.mock import patch, MagicMock

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="Done")]
        })

        tasks = [
            SubagentTask(
                task_id=f"task-{i}",
                thread_id=f"thread-{i % 3}",
                prompt=f"Test {i}",
                created_at=datetime.now(),
                timeout=60,
            )
            for i in range(6)
        ]

        with patch.object(manager._graph_registry, 'get', return_value=mock_graph):
            for task in tasks:
                await manager.spawn(task)

            await asyncio.sleep(0.2)

            # Check all threads were created
            assert len(manager._threads) == 3
