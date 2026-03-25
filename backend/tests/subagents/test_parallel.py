"""Tests for parallel subagent execution."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.subagents.executor import SubagentStatus
from src.subagents.parallel import (
    ExecutionPhase,
    ParallelExecutor,
    PhasedPlan,
    PhaseResult,
)


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
        from unittest.mock import MagicMock, patch

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

        with patch("src.subagents.parallel.SubagentExecutor") as mock_executor_class:
            mock_executor = mock_executor_class.return_value
            mock_result = MagicMock()
            mock_result.status = SubagentStatus.COMPLETED
            mock_result.result = "test result"
            mock_result.error = None
            mock_executor.aexecute = AsyncMock(return_value=mock_result)

            results = await executor.execute_plan(plan, context={"workspace_id": "test"})

            assert len(results) == 1
            assert results[0].phase_name == "discovery"

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

        with patch("src.subagents.parallel.SubagentExecutor") as mock_executor_class:
            mock_executor = mock_executor_class.return_value
            mock_result = MagicMock()
            mock_result.status = SubagentStatus.COMPLETED
            mock_result.result = {"ok": True}
            mock_result.error = None
            mock_executor.aexecute = AsyncMock(return_value=mock_result)

            results = await executor.execute_plan(
                plan,
                context={"workspace_id": "test"},
                phase_callback=phase_callback,
            )

        assert len(results) == 2
        assert received == ["discovery", "synthesis"]


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
        with patch("src.subagents.parallel.SubagentExecutor") as mock_executor_class:
            mock_executor = mock_executor_class.return_value
            mock_result = MagicMock()
            mock_result.status = MagicMock()
            mock_result.status.value = "completed"
            mock_result.result = "test result"
            mock_result.error = None
            mock_executor.aexecute = AsyncMock(return_value=mock_result)

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
        with patch("src.subagents.parallel.SubagentExecutor") as mock_executor_class:
            mock_executor = mock_executor_class.return_value
            mock_result = MagicMock()
            mock_result.status = SubagentStatus.COMPLETED
            mock_result.result = "test result"
            mock_result.error = None
            mock_executor.aexecute = AsyncMock(return_value=mock_result)

            results = await executor.execute_plan(plan, context={"workspace_id": "test"})

            assert len(results) == 1
            assert results[0].success is True
            assert len(results[0].task_results) == 3
            # Verify all tasks were executed
            assert mock_executor.aexecute.call_count == 3

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
        with patch("src.subagents.parallel.SubagentExecutor") as mock_executor_class:
            mock_executor = mock_executor_class.return_value

            # First call succeeds
            mock_result1 = MagicMock()
            mock_result1.status = SubagentStatus.COMPLETED
            mock_result1.result = "success 1"
            mock_result1.error = None

            # Second call fails
            mock_result2 = MagicMock()
            mock_result2.status = SubagentStatus.FAILED
            mock_result2.result = None
            mock_result2.error = "Task failed"

            mock_executor.aexecute = AsyncMock(side_effect=[mock_result1, mock_result2])

            results = await executor.execute_plan(plan, context={"workspace_id": "test"})

            assert len(results) == 1
            assert results[0].success is False  # Phase should fail if any task fails
            assert len(results[0].task_results) == 2
            assert results[0].task_results[0]["success"] is True
            assert results[0].task_results[1]["success"] is False
