"""Tests for failure handling + retry in LeadAgentRuntime (Task 2.12)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TypedDict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure subagent types are registered before compiler
import src.subagents.v2.types  # noqa: F401

from src.agents.contracts.task_brief import TaskBrief
from src.agents.lead_agent.v2.compiler import _default_runner_factory, compile_graph
from src.agents.lead_agent.v2.runtime import LeadAgentRuntime
from src.subagents.v2.base import SubagentBase, SubagentContext, SubagentResult
from src.subagents.v2.registry import REGISTRY


# ---------------------------------------------------------------------------
# Test state
# ---------------------------------------------------------------------------


class FailureHandlingState(TypedDict, total=False):
    node_results: dict
    workspace_id: str
    execution_id: str
    inputs_for_tasks: dict
    workspace_data: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(**kwargs) -> FailureHandlingState:
    return FailureHandlingState(
        workspace_id="ws-test",
        execution_id="exec-test",
        inputs_for_tasks={},
        workspace_data={},
        node_results={},
        **kwargs,
    )


def _make_brief(capability_id: str = "test_cap") -> TaskBrief:
    return TaskBrief(
        capability_id=capability_id,
        raw_message="test",
        workspace_id="ws-001",
        brief={"topic": "failure test"},
    )


def _make_fake_capability(graph_template: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id="test_cap",
        workspace_type="thesis",
        display_name="Failure Test Cap",
        graph_template=graph_template,
        brief_schema={},
    )


def _make_resolver(cap) -> MagicMock:
    resolver = MagicMock()
    resolver.resolve = AsyncMock(return_value=cap)
    return resolver


SINGLE_PHASE_TEMPLATE = {
    "phases": [
        {
            "name": "outline_phase",
            "tasks": [{"name": "make_outline", "subagent_type": "react"}],
        }
    ]
}


# ---------------------------------------------------------------------------
# Tests for _default_runner_factory retry logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_node_retries_on_failure_and_succeeds():
    """Subagent fails twice then succeeds on 3rd attempt (retry_on_failure=2)."""
    attempt_count = 0

    class FlakySubagent(SubagentBase):
        name = "flaky_test_agent"

        async def run(self, ctx: SubagentContext) -> SubagentResult:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise RuntimeError(f"transient error attempt {attempt_count}")
            return SubagentResult(output={"result": "success"})

    task_spec = {"name": "flaky_task", "retry_on_failure": 2}
    runner = _default_runner_factory(FlakySubagent, task_spec)

    # Patch asyncio.sleep to avoid real delays in tests
    with patch("src.agents.lead_agent.v2.compiler.asyncio.sleep", new_callable=AsyncMock):
        state = _make_state()
        result = await runner(state)

    assert "flaky_task" in result["node_results"]
    assert result["node_results"]["flaky_task"]["output"]["result"] == "success"
    assert attempt_count == 3


@pytest.mark.asyncio
async def test_node_marked_failed_after_retries_exhausted():
    """Subagent always fails; retry_on_failure=1 → 2 attempts then error captured."""
    attempt_count = 0

    class AlwaysFailSubagent(SubagentBase):
        name = "always_fail_test_agent"

        async def run(self, ctx: SubagentContext) -> SubagentResult:
            nonlocal attempt_count
            attempt_count += 1
            raise RuntimeError("permanent failure")

    task_spec = {"name": "fail_task", "retry_on_failure": 1}
    runner = _default_runner_factory(AlwaysFailSubagent, task_spec)

    with patch("src.agents.lead_agent.v2.compiler.asyncio.sleep", new_callable=AsyncMock):
        state = _make_state()
        result = await runner(state)

    # 2 total attempts (1 initial + 1 retry)
    assert attempt_count == 2
    # Error captured in node_results instead of raised
    assert "fail_task" in result["node_results"]
    nr = result["node_results"]["fail_task"]
    assert "error" in nr
    assert "permanent failure" in nr["error"]
    assert "output" not in nr


@pytest.mark.asyncio
async def test_run_status_failed_partial_when_some_nodes_failed():
    """Runtime returns status='failed_partial' when a node has an error in node_results."""
    # Use a capability template with one task (react)
    cap = _make_fake_capability(SINGLE_PHASE_TEMPLATE)
    resolver = _make_resolver(cap)

    # Create a runner_factory that always produces an error result
    def always_error_factory(subagent_cls, task_spec):
        async def error_node(state: dict) -> dict:
            node_results = dict(state.get("node_results", {}))
            node_results[task_spec["name"]] = {"error": "node always fails"}
            return {"node_results": node_results}
        return error_node

    runtime = LeadAgentRuntime(
        resolver=resolver,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    # Patch compile_graph to use our error factory
    with patch(
        "src.agents.lead_agent.v2.runtime.compile_graph",
        wraps=lambda template, state_class, abort_check=None, skills=None: compile_graph(
            template,
            state_class=state_class,
            runner_factory=always_error_factory,
            abort_check=abort_check,
            skills=skills,
        ),
    ):
        brief = _make_brief()
        report = await runtime.run_session(execution_id="exec-fail-partial", brief=brief)

    assert report.status == "failed_partial"
    assert len(report.errors) == 1
    assert report.errors[0].task == "make_outline"
    assert report.errors[0].phase == "outline_phase"
    assert "node always fails" in report.errors[0].error


@pytest.mark.asyncio
async def test_run_status_completed_when_all_succeed():
    """Runtime returns status='completed' when all nodes succeed."""
    cap = _make_fake_capability(SINGLE_PHASE_TEMPLATE)
    resolver = _make_resolver(cap)

    runtime = LeadAgentRuntime(
        resolver=resolver,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    brief = _make_brief()
    report = await runtime.run_session(execution_id="exec-success-all", brief=brief)

    assert report.status == "completed"
    assert report.errors == []


@pytest.mark.asyncio
async def test_node_no_retry_by_default_on_failure():
    """Without retry_on_failure set, a failing node is captured as error after 1 attempt."""
    attempt_count = 0

    class FailOnceSubagent(SubagentBase):
        name = "fail_once_no_retry_agent"

        async def run(self, ctx: SubagentContext) -> SubagentResult:
            nonlocal attempt_count
            attempt_count += 1
            raise ValueError("fail no retry")

    task_spec = {"name": "no_retry_task"}  # no retry_on_failure key
    runner = _default_runner_factory(FailOnceSubagent, task_spec)

    state = _make_state()
    result = await runner(state)

    # Only 1 attempt (max_attempts = 0+1 = 1)
    assert attempt_count == 1
    nr = result["node_results"]["no_retry_task"]
    assert "error" in nr
    assert "fail no retry" in nr["error"]
