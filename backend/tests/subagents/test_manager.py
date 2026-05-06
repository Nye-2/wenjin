"""Tests for GlobalSubagentManager and ThreadContext."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import tool

from src.subagents.manager import (
    GlobalSubagentManager,
    SubagentAccessError,
    ThreadContext,
)
from src.subagents.models import (
    SubagentResult,
    SubagentStatus,
    SubagentTask,
)


def _make_test_tool(name: str):
    @tool(name)
    def _test_tool(query: str) -> str:
        """Return the provided query for test assertions."""
        return query

    return _test_tool


class TestThreadContext:
    def test_create_context(self):
        ctx = ThreadContext(thread_id="thread-1", max_concurrent=3)
        assert ctx.thread_id == "thread-1"
        assert ctx.total_tasks == 0

    def test_create_context_with_owner(self):
        ctx = ThreadContext(
            thread_id="thread-1",
            max_concurrent=3,
            owner_user_id="user-1",
        )
        assert ctx.owner_user_id == "user-1"

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
        manager._load_thread_binding = AsyncMock(
            side_effect=lambda thread_id: (
                {
                    "owner_user_id": "user-1",
                    "workspace_id": "ws-1" if thread_id == "thread-ctx" else None,
                    "skill_id": "framework-designer" if thread_id == "thread-status" else None,
                    "skill_name": "框架大纲" if thread_id == "thread-status" else None,
                }
                if thread_id
                in {
                    "thread-ctx",
                    "owned-thread",
                    "shared-thread",
                    "thread-status",
                    "thread-1",
                }
                else None
            )
        )
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
        from unittest.mock import MagicMock, patch

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

        from unittest.mock import MagicMock, patch

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

        from unittest.mock import MagicMock, patch

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
    async def test_wait_for_completion_returns_terminal_result(self, manager):
        """Waiting on a spawned task should yield the persisted terminal result."""
        task = SubagentTask(
            task_id="wait-test",
            thread_id="thread-result",
            prompt="Test",
            created_at=datetime.now(),
            timeout=60,
        )

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={"messages": [MagicMock(content="Success")]}
        )

        with patch.object(manager._graph_registry, "get", return_value=mock_graph):
            await manager.spawn(task)
            result = await manager.wait_for_completion("thread-result", "wait-test")

        assert result is not None
        assert result.status == SubagentStatus.COMPLETED
        assert result.output == "Success"

    @pytest.mark.asyncio
    async def test_execute_task_passes_runtime_context(self, manager):
        """Manager execution should forward canonical runtime ids into graph config."""
        task = SubagentTask(
            task_id="ctx-test",
            thread_id="thread-ctx",
            prompt="Test",
            created_at=datetime.now(),
            timeout=60,
            max_turns=7,
            metadata={
                "workspace_id": "ws-1",
                "user_id": "user-1",
                "execution_session_id": "exec-1",
                "model_name": "gpt-4o",
            },
        )

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={"messages": [MagicMock(content="Success")]}
        )

        with patch.object(manager._graph_registry, "get", return_value=mock_graph):
            result = await manager._execute_task(task)

        assert result.status == SubagentStatus.COMPLETED
        assert mock_graph.ainvoke.await_args.kwargs["config"] == {
            "recursion_limit": 7,
            "configurable": {
                "thread_id": "thread-ctx",
                "workspace_id": "ws-1",
                "user_id": "user-1",
                "execution_session_id": "exec-1",
                "model_name": "gpt-4o",
            }
        }

    @pytest.mark.asyncio
    async def test_execute_task_collects_token_usage_metadata(self, manager):
        """Completed subagent results should carry normalized token usage metadata."""
        task = SubagentTask(
            task_id="usage-test",
            thread_id="thread-ctx",
            prompt="Test",
            created_at=datetime.now(),
            timeout=60,
            metadata={"model_name": "gpt-4.1-mini"},
        )

        usage_message = MagicMock(content="Done")
        usage_message.usage_metadata = {
            "input_tokens": 30,
            "output_tokens": 6,
            "total_tokens": 36,
        }
        usage_message.response_metadata = {}
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={"messages": [usage_message]})

        with patch.object(manager._graph_registry, "get", return_value=mock_graph):
            result = await manager._execute_task(task)

        assert result.status == SubagentStatus.COMPLETED
        assert result.metadata["token_usage"]["input_tokens"] == 30
        assert result.metadata["token_usage"]["output_tokens"] == 6
        assert result.metadata["token_usage"]["total_tokens"] == 36
        assert result.metadata["model_name"] == "gpt-4.1-mini"

    def test_build_graph_cache_key_includes_model_name(self):
        """Task graph cache must isolate runs with different models."""
        task = SubagentTask(
            task_id="cache-test",
            thread_id="thread-ctx",
            prompt="Test",
            created_at=datetime.now(),
            metadata={"model_name": "gpt-4o"},
        )

        cache_key = GlobalSubagentManager._build_graph_cache_key(task)

        assert "gpt-4o" in cache_key

    @pytest.mark.asyncio
    async def test_create_task_graph_uses_task_specific_model(self, manager):
        """Per-task model overrides should bypass the manager default model."""
        task = SubagentTask(
            task_id="model-override",
            thread_id="thread-ctx",
            prompt="Test",
            created_at=datetime.now(),
            metadata={"model_name": "gpt-4o"},
        )

        custom_llm = MagicMock()

        with patch(
            "src.models.factory.create_chat_model",
            return_value=custom_llm,
        ) as mock_create_model, patch(
            "src.subagents.manager.create_default_subagent_graph",
            return_value=MagicMock(),
        ) as mock_create_graph:
            manager._create_task_graph(task)

        mock_create_model.assert_called_once_with("gpt-4o", thinking_enabled=False)
        assert mock_create_graph.call_args.args[0] is custom_llm

    @pytest.mark.asyncio
    async def test_execute_task_uses_task_specific_prompt_and_tool_subset(self, manager):
        """Manager should honor per-task system prompts and resolved tool subsets."""
        task = SubagentTask(
            task_id="agent-specific",
            thread_id="thread-ctx",
            prompt="Search papers",
            created_at=datetime.now(),
            timeout=60,
            tools=["search_reference_text_units"],
            metadata={"system_prompt": "You are Scout."},
        )
        manager._tools = {
            "search_reference_text_units": _make_test_tool("search_reference_text_units"),
            "read_file": _make_test_tool("read_file"),
        }

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={"messages": [MagicMock(content="Success")]}
        )

        with patch.object(manager._graph_registry, "get", return_value=None), patch(
            "src.subagents.manager.create_academic_agent_graph",
            return_value=mock_graph,
        ) as mock_create:
            result = await manager._execute_task(task)

        assert result.status == SubagentStatus.COMPLETED
        mock_create.assert_called_once()
        assert mock_create.call_args.args[1] == [manager._tools["search_reference_text_units"]]
        assert mock_create.call_args.args[2] == "You are Scout."

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

        from unittest.mock import MagicMock, patch

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

    @pytest.mark.asyncio
    async def test_spawn_syncs_thread_agent_status_with_active_subagent_count(self, manager):
        """Thread status cache should reflect active and completed subagent work."""
        task = SubagentTask(
            task_id="status-test",
            thread_id="thread-status",
            prompt="Test",
            created_at=datetime.now(),
            timeout=60,
        )

        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_invoke(*args, **kwargs):
            started.set()
            await release.wait()
            return {"messages": [MagicMock(content="Done")]}

        mock_graph = MagicMock()
        mock_graph.ainvoke = slow_invoke

        with patch.object(manager._graph_registry, "get", return_value=mock_graph), \
             patch("src.services.thread_events.set_thread_status", new=AsyncMock()) as mock_set_status:
            await manager.spawn(task)
            await asyncio.wait_for(started.wait(), timeout=1)

            mock_set_status.assert_any_await(
                None,
                "thread-status",
                status="running",
                skill="framework-designer",
                skill_name="框架大纲",
                subagent_count=1,
            )

            release.set()
            await asyncio.sleep(0.1)

            mock_set_status.assert_any_await(
                None,
                "thread-status",
                status="completed",
                skill="framework-designer",
                skill_name="框架大纲",
                subagent_count=0,
            )

    @pytest.mark.asyncio
    async def test_publish_subagent_update_includes_canonical_activity(self, manager):
        """Subagent workspace events should carry an activity payload for the timeline."""
        task = SubagentTask(
            task_id="subagent-1",
            thread_id="thread-1",
            prompt="Review the paper",
            created_at=datetime.now(),
            timeout=60,
            metadata={
                "subagent_type": "paper_critic",
                "execution_session_id": "exec-1",
                "workflow_phase": "discovery",
                "workflow_phase_index": "0",
                "workflow_task_index": "1",
                "workflow_strategy": "deep_research:research_discovery",
            },
        )
        result = SubagentResult(
            task_id="subagent-1",
            status=SubagentStatus.COMPLETED,
            output="Found three revision points",
            error=None,
            duration_seconds=1.2,
            metadata={
                "token_usage": {
                    "input_tokens": 42,
                    "output_tokens": 8,
                    "total_tokens": 50,
                },
                "model_name": "gpt-4.1-mini",
            },
        )
        activity = {
            "id": "subagent:subagent-1",
            "kind": "subagent_task",
            "workspace_id": "ws-1",
            "occurred_at": datetime.now().isoformat(),
            "title": "Paper Critic",
            "summary": "Found three revision points",
            "status": "completed",
            "thread_id": "thread-1",
            "task_id": "subagent-1",
            "artifact_id": None,
            "feature_id": None,
            "subagent_type": "paper_critic",
            "metadata": {},
        }

        with patch("src.workspace_events.publish_workspace_event", new=AsyncMock()) as publish_workspace_event:
            await manager._publish_subagent_update(
                "ws-1",
                task,
                status="completed",
                result=result,
                activity=activity,
            )

        payload = publish_workspace_event.await_args.args[2]
        assert payload["activity"]["id"] == "subagent:subagent-1"
        assert payload["activity"]["kind"] == "subagent_task"
        assert payload["activity"]["summary"] == "Found three revision points"
        assert payload["subagent"]["execution_session_id"] == "exec-1"
        assert payload["subagent"]["workflow_phase"] == "discovery"
        assert payload["subagent"]["workflow_phase_index"] == "0"
        assert payload["subagent"]["workflow_task_index"] == "1"
        assert payload["subagent"]["workflow_strategy"] == "deep_research:research_discovery"
        assert payload["subagent"]["token_usage"]["total_tokens"] == 50
        assert payload["subagent"]["model_name"] == "gpt-4.1-mini"

    @pytest.mark.asyncio
    async def test_persist_subagent_activity_uses_durable_record_timestamp(self, manager):
        """Durable subagent projection should drive the canonical activity payload."""
        task = SubagentTask(
            task_id="subagent-persisted",
            thread_id="thread-1",
            prompt="Review the paper",
            created_at=datetime.now(),
            timeout=60,
            metadata={
                "subagent_type": "paper_critic",
                "workspace_id": "ws-1",
            },
        )
        result = SubagentResult(
            task_id="subagent-persisted",
            status=SubagentStatus.TIMED_OUT,
            output=None,
            error="Timed out after 60s",
            duration_seconds=60,
        )
        completed_at = datetime.now()
        persisted_record = MagicMock(
            id="subagent-persisted",
            workspace_id="ws-1",
            thread_id="thread-1",
            status="timed_out",
            subagent_type="paper_critic",
            prompt="Review the paper",
            output_preview=None,
            error="Timed out after 60s",
            created_at=task.created_at,
            updated_at=completed_at,
            completed_at=completed_at,
        )
        mock_store = AsyncMock()
        mock_store.upsert_task_record = AsyncMock(return_value=persisted_record)
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.database.get_db_session", return_value=ctx),
            patch("src.subagents.store.SubagentTaskStore", return_value=mock_store),
        ):
            activity = await manager._persist_subagent_activity(
                task,
                status="timed_out",
                result=result,
            )

        assert activity is not None
        assert activity["status"] == "timed_out"
        assert activity["occurred_at"] == completed_at.isoformat()
        assert activity["summary"] == "Timed out after 60s"

    @pytest.mark.asyncio
    async def test_thread_access_isolated_by_user(self, manager):
        """Users should not access another user's thread context."""
        task = SubagentTask(
            task_id="owned-task",
            thread_id="owned-thread",
            prompt="Test",
            created_at=datetime.now(),
            timeout=60,
            metadata={"user_id": "user-1"},
        )

        from unittest.mock import MagicMock, patch

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="Done")]
        })

        with patch.object(manager._graph_registry, 'get', return_value=mock_graph):
            await manager.spawn(task)
            await asyncio.sleep(0.1)

            own_status = await manager.get_status(
                "owned-thread",
                "owned-task",
                user_id="user-1",
            )
            foreign_status = await manager.get_status(
                "owned-thread",
                "owned-task",
                user_id="user-2",
            )

            assert own_status == SubagentStatus.COMPLETED
            assert foreign_status is None

    @pytest.mark.asyncio
    async def test_spawn_rejects_reusing_thread_id_across_users(self, manager):
        """A thread id owned by one user cannot be reused by another."""
        first_task = SubagentTask(
            task_id="task-1",
            thread_id="shared-thread",
            prompt="First",
            created_at=datetime.now(),
            timeout=60,
            metadata={"user_id": "user-1"},
        )
        second_task = SubagentTask(
            task_id="task-2",
            thread_id="shared-thread",
            prompt="Second",
            created_at=datetime.now(),
            timeout=60,
            metadata={"user_id": "user-2"},
        )

        from unittest.mock import MagicMock, patch

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="Done")]
        })

        with patch.object(manager._graph_registry, 'get', return_value=mock_graph):
            await manager.spawn(first_task)
            with pytest.raises(SubagentAccessError, match="Thread not found"):
                await manager.spawn(second_task)

    @pytest.mark.asyncio
    async def test_spawn_rejects_missing_canonical_thread(self, manager):
        """Manager should not seed context from a missing thread id."""
        task = SubagentTask(
            task_id="missing-thread-task",
            thread_id="missing-thread",
            prompt="Test",
            created_at=datetime.now(),
            timeout=60,
            metadata={"user_id": "user-1"},
        )
        manager._load_thread_binding = AsyncMock(return_value=None)

        with pytest.raises(SubagentAccessError, match="Thread not found"):
            await manager.spawn(task)

    @pytest.mark.asyncio
    async def test_spawn_rejects_workspace_mismatch_against_thread_binding(self, manager):
        """Task metadata workspace must match the canonical thread binding."""
        task = SubagentTask(
            task_id="workspace-mismatch-task",
            thread_id="thread-ctx",
            prompt="Test",
            created_at=datetime.now(),
            timeout=60,
            metadata={"user_id": "user-1", "workspace_id": "ws-2"},
        )
        manager._load_thread_binding = AsyncMock(
            return_value={
                "owner_user_id": "user-1",
                "workspace_id": "ws-1",
            }
        )

        with pytest.raises(SubagentAccessError, match="Thread not found"):
            await manager.spawn(task)

    @pytest.mark.asyncio
    async def test_get_status_falls_back_to_persisted_record(self, manager):
        """Durable subagent records should remain queryable after in-memory context is gone."""
        persisted = MagicMock(
            id="task-persisted",
            thread_id="thread-1",
            status="completed",
            output_preview="Persisted output",
            error=None,
            user_id="user-1",
        )
        manager._load_persisted_task_record = AsyncMock(return_value=persisted)

        status = await manager.get_status("thread-1", "task-persisted", user_id="user-1")
        result = await manager.get_result("thread-1", "task-persisted", user_id="user-1")

        assert status == SubagentStatus.COMPLETED
        assert result is not None
        assert result.output == "Persisted output"
        assert result.metadata["durable_preview"] is True

    @pytest.mark.asyncio
    async def test_check_thread_access_falls_back_to_thread_binding(self, manager):
        """Access checks should honor canonical thread ownership even without live context."""
        manager._threads.clear()

        own_access = await manager.check_thread_access("thread-1", user_id="user-1")
        foreign_access = await manager.check_thread_access("thread-1", user_id="user-2")

        assert own_access is True
        assert foreign_access is False

    @pytest.mark.asyncio
    async def test_list_thread_tasks_returns_recent_task_summaries(self, manager):
        """Thread activity consumers should be able to inspect recent subagent tasks."""
        task = SubagentTask(
            task_id="task-1",
            thread_id="thread-1",
            prompt="Search for recent papers on retrieval augmentation",
            created_at=datetime.now(),
            timeout=60,
            metadata={"user_id": "user-1", "subagent_type": "scout"},
        )

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="Found three relevant papers.")]
        })

        with patch.object(manager._graph_registry, "get", return_value=mock_graph):
            await manager.spawn(task)
            await asyncio.sleep(0.1)

            summaries = await manager.list_thread_tasks(
                "thread-1",
                user_id="user-1",
            )

        assert len(summaries) == 1
        assert summaries[0]["task_id"] == "task-1"
        assert summaries[0]["subagent_type"] == "scout"
        assert summaries[0]["status"] == "completed"
        assert "Found three relevant papers." in (summaries[0]["output_preview"] or "")
