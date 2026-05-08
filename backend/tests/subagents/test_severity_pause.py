"""Spec §6.3 — high-criticality subagent failures auto-pause the run.

Severity routing:
- low (default): subagent.status="failed" surfaces in payload, run continues
- high: failed subagent triggers ParallelExecutor.pause() so the lead agent
  can emit a question_card asking the user how to proceed before the next
  phase begins.

Criticality is read from the task dict (`task["criticality"] in {"low","high"}`)
because at the executor level tasks are still raw dicts, not SubagentTask
dataclass instances.
"""
from unittest.mock import AsyncMock, patch

import pytest

from src.subagents.models import SubagentResult, SubagentStatus
from src.subagents.parallel import (
    ExecutionPhase,
    ParallelExecutor,
    PhasedPlan,
)


def _manager_with_failure(error: str = "boom"):
    """Subagent that resolves to FAILED."""
    from unittest.mock import MagicMock
    manager = MagicMock()
    manager._llm = object()
    manager._config.default_timeout = 900
    manager._config.max_turns_limit = 50
    manager.spawn = AsyncMock(return_value="task-1")
    manager.wait_for_completion = AsyncMock(
        return_value=SubagentResult(
            task_id="task-1",
            status=SubagentStatus.FAILED,
            output=None,
            error=error,
        )
    )
    return manager


@pytest.mark.asyncio
async def test_high_criticality_failure_pauses_run():
    executor = ParallelExecutor(max_concurrent=2)
    plan = PhasedPlan(phases=[
        ExecutionPhase(
            name="critical_phase",
            tasks=[{"subagent_type": "scout", "prompt": "x", "criticality": "high"}],
        ),
    ])

    with patch("src.subagents.parallel.get_manager", return_value=_manager_with_failure()):
        await executor.execute_plan(
            plan,
            context={"workspace_id": "test", "execution_session_id": "exec-1"},
        )

    assert not executor._pause_event.is_set(), "high-criticality failure must auto-pause"


@pytest.mark.asyncio
async def test_low_criticality_failure_does_not_pause():
    executor = ParallelExecutor(max_concurrent=2)
    plan = PhasedPlan(phases=[
        ExecutionPhase(
            name="non_critical",
            tasks=[{"subagent_type": "scout", "prompt": "x", "criticality": "low"}],
        ),
    ])

    with patch("src.subagents.parallel.get_manager", return_value=_manager_with_failure()):
        await executor.execute_plan(
            plan,
            context={"workspace_id": "test", "execution_session_id": "exec-1"},
        )

    assert executor._pause_event.is_set(), "low-criticality failure must not pause"


@pytest.mark.asyncio
async def test_missing_criticality_defaults_to_low():
    """Tasks created before T11 don't carry criticality — treat as low."""
    executor = ParallelExecutor(max_concurrent=2)
    plan = PhasedPlan(phases=[
        ExecutionPhase(
            name="legacy_phase",
            tasks=[{"subagent_type": "scout", "prompt": "x"}],  # no criticality field
        ),
    ])

    with patch("src.subagents.parallel.get_manager", return_value=_manager_with_failure()):
        await executor.execute_plan(
            plan,
            context={"workspace_id": "test", "execution_session_id": "exec-1"},
        )

    assert executor._pause_event.is_set()


@pytest.mark.asyncio
async def test_successful_high_criticality_task_does_not_pause():
    """Pause is triggered by FAILURE, not by criticality alone."""
    from unittest.mock import MagicMock
    manager = MagicMock()
    manager._llm = object()
    manager._config.default_timeout = 900
    manager._config.max_turns_limit = 50
    manager.spawn = AsyncMock(return_value="task-1")
    manager.wait_for_completion = AsyncMock(
        return_value=SubagentResult(
            task_id="task-1",
            status=SubagentStatus.COMPLETED,
            output="ok",
            error=None,
        )
    )

    executor = ParallelExecutor(max_concurrent=2)
    plan = PhasedPlan(phases=[
        ExecutionPhase(
            name="critical_ok",
            tasks=[{"subagent_type": "scout", "prompt": "x", "criticality": "high"}],
        ),
    ])

    with patch("src.subagents.parallel.get_manager", return_value=manager):
        await executor.execute_plan(
            plan,
            context={"workspace_id": "test", "execution_session_id": "exec-1"},
        )

    assert executor._pause_event.is_set()
