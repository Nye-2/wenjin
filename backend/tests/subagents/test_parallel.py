"""Tests for parallel subagent execution."""

import asyncio

import pytest

from src.subagents.parallel import (
    ParallelExecutor,
    ExecutionPhase,
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

        # Mock the subagent executor - execute is synchronous, not async
        with patch("src.subagents.parallel.SubagentExecutor") as mock_executor_class:
            mock_executor = mock_executor_class.return_value
            mock_result = MagicMock()
            mock_result.status = MagicMock()
            mock_result.status.value = "completed"
            mock_result.result = "test result"
            mock_result.error = None
            mock_executor.execute = MagicMock(return_value=mock_result)

            results = await executor.execute_plan(plan, context={"workspace_id": "test"})

            assert len(results) == 1
            assert results[0].phase_name == "discovery"


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
