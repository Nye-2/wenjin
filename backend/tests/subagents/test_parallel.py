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
            results = await executor.execute_plan(
                plan,
                context={"workspace_id": "test", "execution_session_id": "exec-1"},
            )

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
                context={"workspace_id": "test", "execution_session_id": "exec-1"},
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
                context={"workspace_id": "ws-1", "execution_session_id": "exec-1"},
            )

        task = mock_manager.spawn.await_args.args[0]
        assert task.thread_id == "thread-1"
        assert task.metadata["workspace_id"] == "ws-1"
        assert task.metadata["user_id"] == "user-1"
        assert task.metadata["execution_session_id"] == "exec-1"
        assert task.metadata["model_name"] == "gpt-4o"
        assert task.metadata["workflow_phase"] == "discovery"
        assert task.metadata["workflow_phase_index"] == "0"
        assert task.metadata["workflow_task_index"] == "0"

    @pytest.mark.asyncio
    async def test_execute_plan_routes_model_name(self):
        """Parallel execution should route model_name through shared subagent routing."""
        executor = ParallelExecutor()
        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="discovery",
                    tasks=[{"subagent_type": "scout", "prompt": "test search"}],
                ),
            ],
            context={"model_name": "gen-fallback"},
        )
        mock_manager = _make_manager(output='{"papers": []}')

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager), patch(
            "src.subagents.parallel.route_subagent_model",
            return_value="tool-primary",
        ) as route_mock:
            await executor.execute_plan(
                plan,
                context={"workspace_id": "ws-1", "execution_session_id": "exec-1"},
            )

        route_mock.assert_called_once_with(thread_model="gen-fallback")
        task = mock_manager.spawn.await_args.args[0]
        assert task.metadata["model_name"] == "tool-primary"

    @pytest.mark.asyncio
    async def test_execute_plan_applies_subagent_timeout_override(self):
        """Per-type timeout/max_turns overrides should flow into spawned task limits."""
        executor = ParallelExecutor()
        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="discovery",
                    tasks=[{"subagent_type": "scout", "prompt": "test search"}],
                ),
            ],
        )
        mock_manager = _make_manager(output='{"papers": []}')
        override_config = MagicMock(
            max_turns=12,
            timeout=321,
            tools=["search_reference_text_units"],
            system_prompt="prompt",
        )

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager), patch(
            "src.subagents.parallel.get_subagent_config",
            return_value=override_config,
        ):
            await executor.execute_plan(
                plan,
                context={"workspace_id": "ws-1", "execution_session_id": "exec-1"},
            )

        task = mock_manager.spawn.await_args.args[0]
        assert task.max_turns == 12
        assert task.timeout == 321

    @pytest.mark.asyncio
    async def test_execute_plan_propagates_workflow_strategy_and_phase_indexes(self):
        """Subagent metadata should carry workflow strategy and phase indexes for tracing."""
        executor = ParallelExecutor()
        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="discovery",
                    tasks=[
                        {"subagent_type": "scout", "prompt": "search A"},
                        {"subagent_type": "scout", "prompt": "search B"},
                    ],
                ),
                ExecutionPhase(
                    name="synthesis",
                    tasks=[{"subagent_type": "synthesizer", "prompt": "synthesize"}],
                    depends_on=["discovery"],
                ),
            ],
        )
        mock_manager = _make_manager(output={"ok": True})

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            await executor.execute_plan(
                plan,
                context={
                    "workspace_id": "ws-1",
                    "thread_id": "thread-1",
                    "execution_session_id": "exec-1",
                    "workflow_strategy": "deep_research:research_discovery",
                },
            )

        spawned = [call.args[0] for call in mock_manager.spawn.await_args_list]
        assert len(spawned) == 3
        discovery_tasks = [
            task for task in spawned if task.metadata.get("workflow_phase") == "discovery"
        ]
        synthesis_tasks = [
            task for task in spawned if task.metadata.get("workflow_phase") == "synthesis"
        ]
        assert len(discovery_tasks) == 2
        assert len(synthesis_tasks) == 1
        assert {task.metadata.get("workflow_task_index") for task in discovery_tasks} == {"0", "1"}
        assert synthesis_tasks[0].metadata.get("workflow_phase_index") == "1"
        assert all(
            task.metadata.get("workflow_strategy") == "deep_research:research_discovery"
            for task in spawned
        )

    @pytest.mark.asyncio
    async def test_execute_plan_requires_execution_session_id(self):
        """Subagent execution no longer supports detached session-less plans."""
        executor = ParallelExecutor()
        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="discovery",
                    tasks=[{"subagent_type": "scout", "prompt": "test search"}],
                ),
            ],
        )
        mock_manager = _make_manager(output='{"papers": []}')

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            results = await executor.execute_plan(
                plan,
                context={"workspace_id": "ws-1"},
            )

        assert len(results) == 1
        assert results[0].success is False
        assert "missing execution_session_id" in str(results[0].task_results[0]["error"]).lower()
        mock_manager.spawn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_execute_plan_requires_llm_or_routed_model(self):
        """Planner should fail when manager has no llm and model routing returns none."""
        executor = ParallelExecutor()
        plan = PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="discovery",
                    tasks=[{"subagent_type": "scout", "prompt": "test search"}],
                ),
            ],
        )
        mock_manager = _make_manager(output='{"papers": []}')
        mock_manager._llm = None

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager), patch(
            "src.subagents.parallel.route_subagent_model",
            return_value=None,
        ):
            results = await executor.execute_plan(
                plan,
                context={"workspace_id": "ws-1", "execution_session_id": "exec-1"},
            )

        assert len(results) == 1
        assert results[0].success is False
        assert "no thread model is configured" in str(results[0].task_results[0]["error"]).lower()
        mock_manager.spawn.assert_not_awaited()


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
            results = await executor.execute_plan(
                plan,
                context={"workspace_id": "test", "execution_session_id": "exec-1"},
            )

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
            results = await executor.execute_plan(
                plan,
                context={"workspace_id": "test", "execution_session_id": "exec-1"},
            )

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
            results = await executor.execute_plan(
                plan,
                context={"workspace_id": "test", "execution_session_id": "exec-1"},
            )
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
            await executor.execute_plan(
                plan,
                context={"workspace_id": "test", "execution_session_id": "exec-1"},
            )

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

        # Mock config resolver to raise for unknown type
        with patch("src.subagents.parallel.get_subagent_config") as mock_get:
            mock_get.side_effect = ValueError("Unknown subagent type")

            results = await executor.execute_plan(
                plan,
                context={"workspace_id": "test", "execution_session_id": "exec-1"},
            )

            mock_get.assert_called_once_with(
                "unknown_type",
                apply_runtime_overrides=True,
            )
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
            results = await executor.execute_plan(
                plan,
                context={"workspace_id": "test", "execution_session_id": "exec-1"},
            )

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
            results = await executor.execute_plan(
                plan,
                context={"workspace_id": "test", "execution_session_id": "exec-1"},
            )

        assert len(results) == 1
        assert results[0].success is False  # Phase should fail if any task fails
        assert len(results[0].task_results) == 2
        assert results[0].task_results[0]["success"] is True
        assert results[0].task_results[1]["success"] is False


class TestParallelExecutorFailFast:
    @pytest.mark.asyncio
    async def test_fail_fast_skips_dependent_phases(self):
        """When fail_fast=True, phases depending on a failed phase should be skipped."""
        executor = ParallelExecutor(fail_fast=True)
        plan = PhasedPlan(
            phases=[
                ExecutionPhase(name="phase1", tasks=[{"subagent_type": "scout", "prompt": "task"}]),
                ExecutionPhase(name="phase2", tasks=[{"subagent_type": "synthesizer", "prompt": "task"}], depends_on=["phase1"]),
            ],
        )
        mock_manager = _make_manager(status=SubagentStatus.FAILED, output=None, error="task failed")
        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            results = await executor.execute_plan(
                plan,
                context={"workspace_id": "test", "execution_session_id": "exec-1"},
            )
        assert len(results) == 2
        assert results[0].success is False
        assert results[1].success is False
        assert "skipped" in results[1].error.lower()

    @pytest.mark.asyncio
    async def test_fail_fast_default_is_false(self):
        """Default fail_fast should be False."""
        executor = ParallelExecutor()
        assert executor.fail_fast is False

    @pytest.mark.asyncio
    async def test_fail_fast_false_continues_after_failure(self):
        """When fail_fast=False, dependent phases still execute."""
        executor = ParallelExecutor(fail_fast=False)
        plan = PhasedPlan(
            phases=[
                ExecutionPhase(name="phase1", tasks=[{"subagent_type": "scout", "prompt": "task"}]),
                ExecutionPhase(name="phase2", tasks=[{"subagent_type": "scout", "prompt": "task"}], depends_on=["phase1"]),
            ],
        )
        call_count = 0

        async def varying_result(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return SubagentResult(task_id="t1", status=SubagentStatus.FAILED, output=None, error="failed")
            return SubagentResult(task_id="t2", status=SubagentStatus.COMPLETED, output="ok", error=None)

        mock_manager = _make_manager()
        mock_manager.wait_for_completion = AsyncMock(side_effect=varying_result)
        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            results = await executor.execute_plan(
                plan,
                context={"workspace_id": "test", "execution_session_id": "exec-1"},
            )
        assert len(results) == 2
        assert results[0].success is False
        assert results[1].success is True  # Still executed


class TestParallelExecutorStress:
    @pytest.mark.asyncio
    async def test_high_fanout_plan_respects_concurrency_limit(self):
        """Stress case: high fanout plans should respect executor semaphore limits."""
        max_concurrent = 3
        executor = ParallelExecutor(max_concurrent=max_concurrent)
        fanout_tasks = [
            {"subagent_type": "scout", "prompt": f"task {index}"}
            for index in range(24)
        ]
        plan = PhasedPlan(
            phases=[
                ExecutionPhase(name="fanout", tasks=fanout_tasks),
            ],
        )

        mock_manager = _make_manager(output={"ok": True})
        in_flight = 0
        observed_peak = 0
        task_seq = 0

        async def _wait_for_completion(*_args, **_kwargs):
            nonlocal in_flight, observed_peak, task_seq
            task_seq += 1
            in_flight += 1
            observed_peak = max(observed_peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return SubagentResult(
                task_id=f"task-{task_seq}",
                status=SubagentStatus.COMPLETED,
                output={"task": task_seq},
                error=None,
            )

        mock_manager.wait_for_completion = AsyncMock(side_effect=_wait_for_completion)

        with patch("src.subagents.parallel.get_manager", return_value=mock_manager):
            results = await executor.execute_plan(
                plan,
                context={
                    "workspace_id": "ws-stress",
                    "thread_id": "thread-stress",
                    "execution_session_id": "exec-stress",
                },
            )

        assert len(results) == 1
        assert results[0].success is True
        assert len(results[0].task_results) == 24
        assert mock_manager.spawn.await_count == 24
        assert observed_peak <= max_concurrent
