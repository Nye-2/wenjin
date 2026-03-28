"""Tests for parallel subagent execution."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.subagents.models import SubagentResult, SubagentStatus
from src.subagents.parallel import (
    ExecutionPhase,
    ParallelExecutor,
    PhasedPlan,
    PhaseResult,
)


def _make_manager(
    *,
    status: SubagentStatus = SubagentStatus.COMPLETED,
    output=None,
    error: str | None = None,
):
    manager = MagicMock()
    manager._llm = object()
    manager._config.default_timeout = 900
    manager._config.max_turns_limit = 50
    manager.spawn = AsyncMock(return_value="task-123")
    manager.wait_for_completion = AsyncMock(
        return_value=SubagentResult(
            task_id="task-123",
            status=status,
            output=output,
            error=error,
        )
    )
    return manager


class TestParallelExecutor:
    def test_execution_phase_creation(self):
        """ExecutionPhase should track subagent tasks."""
        phase = ExecutionPhase(
            name="discovery",
            tasks=[
                {"subagent_type": "scout", "prompt": "Search topic A"},
                {"subagent_type": "scout", "prompt": "Search topic B"},
            ],
        )
        assert phase.name == "discovery"
        assert len(phase.tasks) == 2

    def test_phased_plan_dependencies(self):
        """PhasedPlan should handle phase dependencies."""
        plan = PhasedPlan(
            phases=[
                ExecutionPhase(name="phase1", tasks=[{"subagent_type": "scout", "prompt": "search"}]),
                ExecutionPhase(name="phase2", tasks=[{"subagent_type": "synthesizer", "prompt": "analyze"}], depends_on=["phase1"]),
            ],
        )
        assert len(plan.phases) == 2
        assert plan.phases[1].depends_on == ["phase1"]

    @pytest.mark.asyncio
    async def test_parallel_executor_runs_phases(self):
        """ParallelExecutor should execute phases in order."""
        executor = ParallelExecutor()

        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="discovery",
                    tasks=[
                        {"subagent_type": "scout", "prompt": "test search"},
                    ],
                ),
            ],
        )

        mock_manager = _make_manager(output="test result")

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            results = await executor.execute_plan(plan, context={"workspace_id": "test"})

        assert len(results) == 1
        assert results[0].phase_name == "discovery"
        assert mock_manager.spawn.await_count == 1

    @pytest.mark.asyncio
    async def test_execute_plan_invokes_phase_callback(self):
        """Phase callback should receive each completed phase result in order."""
        executor = ParallelExecutor()
        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="discovery",
                    tasks=[{"subagent_type": "scout", "prompt": "test search"}],
                ),
                ExecutionPhase(
                    name="synthesis",
                    tasks=[{"subagent_type": "synthesizer", "prompt": "test ideas"}],
                    depends_on=["discovery"],
                ),
            ],
        )

        received: list[str] = []

        async def phase_callback(result: PhaseResult) -> None:
            received.append(result.phase_name)

        mock_manager = _make_manager(output='{"ok": true}')

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            results = await executor.execute_plan(
                plan,
                context={"workspace_id": "test"},
                phase_callback=phase_callback,
            )

        assert len(results) == 2
        assert received == ["discovery", "synthesis"]

    @pytest.mark.asyncio
    async def test_execute_plan_merges_plan_context_and_runtime_context(self):
        """Plan context should merge with runtime context before spawning tasks."""
        executor = ParallelExecutor()
        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="discovery",
                    tasks=[{"subagent_type": "scout", "prompt": "test search"}],
                ),
            ],
            context={"thread_id": "thread-1", "user_id": "user-1", "model_name": "gpt-4o"},
        )
        mock_manager = _make_manager(output='{"papers": []}')

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            await executor.execute_plan(
                plan,
                context={"workspace_id": "ws-1"},
            )

        task = mock_manager.spawn.await_args.args[0]
        assert task.thread_id == "thread-1"
        assert task.metadata["workspace_id"] == "ws-1"
        assert task.metadata["user_id"] == "user-1"
        assert task.metadata["model_name"] == "gpt-4o"


class TestExecutionPhase:
    def test_is_parallel(self):
        """Phase with multiple tasks should be parallel."""
        phase = ExecutionPhase(
            name="parallel_search",
            tasks=[
                {"subagent_type": "scout", "prompt": "A"},
                {"subagent_type": "scout", "prompt": "B"},
            ],
        )
        assert phase.is_parallel()

    def test_is_not_parallel_single_task(self):
        """Phase with single task should not be parallel."""
        phase = ExecutionPhase(
            name="single",
            tasks=[{"subagent_type": "scout", "prompt": "A"}],
        )
        assert not phase.is_parallel()


class TestPhaseResult:
    def test_phase_result_success_by_default(self):
        """PhaseResult should default to success=True."""
        result = PhaseResult(
            phase_name="test",
            task_results=[{"success": True}, {"success": True}]
        )
        assert result.success is True
        assert result.error is None

    def test_phase_result_handles_missing_success_key(self):
        """PhaseResult should handle results without 'success' key."""
        result = PhaseResult(
            phase_name="test",
            task_results=[{"success": True}, {}]  # Missing success key
        )
        assert result.success is False  # Should treat missing success as failure

    def test_phase_result_handles_false_success_key(self):
        """PhaseResult should handle results with success=False."""
        result = PhaseResult(
            phase_name="test",
            task_results=[{"success": True}, {"success": False}]
        )
        assert result.success is False

    def test_phase_result_handles_non_dict_results(self):
        """PhaseResult should handle non-dict results as failures."""
        result = PhaseResult(
            phase_name="test",
            task_results=[{"success": True}, "not_a_dict"]
        )
        assert result.success is False


class TestParallelExecutorTimeout:
    @pytest.mark.asyncio
    async def test_phase_timeout_raises_on_slow_task(self):
        """Phase execution should return error when phase_timeout is exceeded."""
        executor = ParallelExecutor(phase_timeout=0.1)

        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="slow_phase",
                    tasks=[{"subagent_type": "scout", "prompt": "slow task"}],
                ),
            ],
        )

        mock_manager = _make_manager(output="result")

        async def _slow_wait(*a, **kw):
            await asyncio.sleep(10)

        mock_manager.wait_for_completion = AsyncMock(side_effect=_slow_wait)

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            results = await executor.execute_plan(plan, context={"workspace_id": "test"})

        assert results[0].success is False
        assert "timed out" in results[0].error.lower()

    @pytest.mark.asyncio
    async def test_phase_timeout_default_is_none(self):
        """Default phase_timeout should be None (no timeout)."""
        executor = ParallelExecutor()
        assert executor.phase_timeout is None

    @pytest.mark.asyncio
    async def test_phase_completes_within_timeout(self):
        """Phase should succeed when completing within timeout."""
        executor = ParallelExecutor(phase_timeout=10.0)

        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="fast_phase",
                    tasks=[{"subagent_type": "scout", "prompt": "fast task"}],
                ),
            ],
        )

        mock_manager = _make_manager(output="quick result")

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            results = await executor.execute_plan(plan, context={"workspace_id": "test"})

        assert results[0].success is True


class TestParallelExecutorNormalization:
    def test_normalize_result_payload_parses_json_object(self):
        payload = ParallelExecutor._normalize_result_payload('{"papers": [{"title": "A"}]}')
        assert payload == {"papers": [{"title": "A"}]}

    def test_normalize_result_payload_parses_fenced_json(self):
        payload = ParallelExecutor._normalize_result_payload(
            "Here is the result:\n```json\n{\"ideas\": [{\"title\": \"A\"}]}\n```"
        )
        assert payload == {"ideas": [{"title": "A"}]}


class TestParallelExecutorIntegration:
    @pytest.mark.asyncio
    async def test_dependency_wait_with_event(self):
        """Test that dependencies wait using asyncio.Event, not busy wait."""
        executor = ParallelExecutor()

        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="phase1",
                    tasks=[{"subagent_type": "scout", "prompt": "first task"}],
                ),
                ExecutionPhase(
                    name="phase2",
                    tasks=[{"subagent_type": "scout", "prompt": "second task"}],
                    depends_on=["phase1"],
                ),
            ],
        )

        # Mock the subagent executor
        mock_manager = _make_manager(output="test result")

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            # Track time to verify we're not using busy wait
            start_time = asyncio.get_event_loop().time()
            results = await executor.execute_plan(plan, context={"workspace_id": "test"})
            end_time = asyncio.get_event_loop().time()

            # Should complete quickly (not sleep for 0.1 multiple times)
            assert (end_time - start_time) < 0.5
            assert len(results) == 2
            assert results[0].phase_name == "phase1"
            assert results[1].phase_name == "phase2"

    @pytest.mark.asyncio
    async def test_missing_phase_dependency_raises_value_error(self):
        """Unknown phase dependencies should fail fast instead of busy waiting forever."""
        executor = ParallelExecutor()
        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="phase1",
                    tasks=[{"subagent_type": "scout", "prompt": "first task"}],
                    depends_on=["missing-phase"],
                ),
            ],
        )

        with pytest.raises(ValueError, match="Unknown phase dependencies"):
            await executor.execute_plan(plan, context={"workspace_id": "test"})

    @pytest.mark.asyncio
    async def test_unknown_subagent_type_error_handling(self):
        """Test handling of unknown subagent types."""
        executor = ParallelExecutor()

        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="test_phase",
                    tasks=[{"subagent_type": "unknown_type", "prompt": "test"}],
                ),
            ],
        )

        # Mock registry to return None for unknown type
        with patch("src.subagents.parallel.registry.get") as mock_get:
            mock_get.return_value = None

            results = await executor.execute_plan(plan, context={"workspace_id": "test"})

            assert len(results) == 1
            assert results[0].success is False
            assert results[0].error is None  # PhaseResult error is None, individual task has error
            assert len(results[0].task_results) == 1
            assert results[0].task_results[0]["success"] is False
            assert results[0].task_results[0]["error"] == "Unknown subagent type: unknown_type"

    @pytest.mark.asyncio
    async def test_parallel_execution_with_multiple_tasks(self):
        """Test execution of parallel tasks in a phase."""
        executor = ParallelExecutor()

        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="parallel_phase",
                    tasks=[
                        {"subagent_type": "scout", "prompt": "task 1"},
                        {"subagent_type": "scout", "prompt": "task 2"},
                        {"subagent_type": "scout", "prompt": "task 3"},
                    ],
                ),
            ],
        )

        # Mock the subagent executor
        mock_manager = _make_manager(output="test result")

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            results = await executor.execute_plan(plan, context={"workspace_id": "test"})

        assert len(results) == 1
        assert results[0].success is True
        assert len(results[0].task_results) == 3
        assert mock_manager.spawn.await_count == 3

    @pytest.mark.asyncio
    async def test_mixed_success_in_parallel_tasks(self):
        """Test phase success with mixed success/failure in parallel tasks."""
        executor = ParallelExecutor()

        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="mixed_phase",
                    tasks=[
                        {"subagent_type": "scout", "prompt": "task 1"},
                        {"subagent_type": "scout", "prompt": "task 2"},
                    ],
                ),
            ],
        )

        # Mock different results for different tasks
        mock_manager = _make_manager()
        mock_manager.wait_for_completion = AsyncMock(
            side_effect=[
                SubagentResult(
                    task_id="task-1",
                    status=SubagentStatus.COMPLETED,
                    output="success 1",
                    error=None,
                ),
                SubagentResult(
                    task_id="task-2",
                    status=SubagentStatus.FAILED,
                    output=None,
                    error="Task failed",
                ),
            ]
        )

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            results = await executor.execute_plan(plan, context={"workspace_id": "test"})

        assert len(results) == 1
        assert results[0].success is False  # Phase should fail if any task fails
        assert len(results[0].task_results) == 2
        assert results[0].task_results[0]["success"] is True
        assert results[0].task_results[1]["success"] is False
