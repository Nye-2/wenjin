from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.harness import (
    AgentHarness,
    AgentSessionRequest,
    NativeWenjinAgentHarness,
    SubtaskRequest,
)
from src.subagents.parallel import ExecutionPhase, PhasedPlan, PhaseResult


def _plan() -> PhasedPlan:
    return PhasedPlan(
        phases=[
            ExecutionPhase(
                name="discovery",
                tasks=[{"subagent_type": "scout", "prompt": "search"}],
            )
        ]
    )


@pytest.mark.asyncio
async def test_native_harness_requires_execution_session_id() -> None:
    harness = NativeWenjinAgentHarness(max_concurrent=1)

    with pytest.raises(ValueError, match="execution_session_id"):
        await harness.run_session(
            AgentSessionRequest(
                strategy="test",
                phased_plan=_plan(),
                context={"workspace_id": "ws-1"},
            )
        )


@pytest.mark.asyncio
async def test_native_harness_runs_bound_session_through_parallel_executor() -> None:
    phase_result = PhaseResult(
        phase_name="discovery",
        task_results=[{"subagent_type": "scout", "success": True, "result": "ok"}],
    )
    executor = SimpleNamespace(execute_plan=AsyncMock(return_value=[phase_result]))

    with patch(
        "src.agents.harness.native.ParallelExecutor",
        return_value=executor,
    ) as executor_cls:
        harness = NativeWenjinAgentHarness(max_concurrent=2)
        result = await harness.run_session(
            AgentSessionRequest(
                strategy="research",
                phased_plan=_plan(),
                context={"execution_session_id": "exec-1", "workspace_id": "ws-1"},
            )
        )

    executor_cls.assert_called_once_with(
        max_concurrent=2,
        phase_timeout=None,
        fail_fast=True,
    )
    assert result.provider == "native_wenjin"
    assert result.strategy == "research"
    assert result.phase_results == [phase_result]
    executor.execute_plan.assert_awaited_once()


@pytest.mark.asyncio
async def test_native_harness_maps_single_subtask_result() -> None:
    phase_result = PhaseResult(
        phase_name="subtask",
        task_results=[
            {
                "subagent_type": "scout",
                "success": True,
                "result": {"summary": "done"},
                "error": None,
            }
        ],
    )
    executor = SimpleNamespace(execute_plan=AsyncMock(return_value=[phase_result]))

    with patch("src.agents.harness.native.ParallelExecutor", return_value=executor):
        harness = NativeWenjinAgentHarness(max_concurrent=1)
        result = await harness.run_subtask(
            SubtaskRequest(
                subagent_type="scout",
                prompt="search",
                context={"execution_session_id": "exec-1"},
            )
        )

    assert isinstance(harness, AgentHarness)
    assert result.subagent_type == "scout"
    assert result.success is True
    assert result.result == {"summary": "done"}
    assert result.error is None
