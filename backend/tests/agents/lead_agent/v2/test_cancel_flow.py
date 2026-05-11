"""Tests for cancel flow in LeadAgentRuntime (Task 2.11)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure subagent types are registered
import src.subagents.v2.types  # noqa: F401

from src.agents.contracts.task_brief import TaskBrief
from src.agents.lead_agent.v2.runtime import ExecutionAborted, LeadAgentRuntime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SIMPLE_GRAPH_TEMPLATE = {
    "phases": [
        {
            "name": "outline_phase",
            "tasks": [
                {
                    "name": "make_outline",
                    "subagent_type": "react",
                    "display_name": "Make Outline",
                }
            ],
        }
    ]
}


def _make_fake_capability():
    return SimpleNamespace(
        id="test_cap",
        workspace_type="thesis",
        display_name="Test Capability",
        graph_template=SIMPLE_GRAPH_TEMPLATE,
        brief_schema={"properties": {}},
    )


def _make_brief():
    return TaskBrief(
        capability_id="test_cap",
        raw_message="write something",
        workspace_id="ws-001",
        brief={"topic": "cancel test"},
    )


def _make_resolver(cap):
    resolver = MagicMock()
    resolver.resolve = AsyncMock(return_value=cap)
    return resolver


def _abort_redis(abort: bool = True) -> MagicMock:
    """Create a mock Redis client that returns abort signal based on 'abort' flag."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value="1" if abort else None)
    return redis


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runtime_aborts_when_signal_set():
    """When the Redis abort signal is set before graph invocation, status='cancelled'."""
    cap = _make_fake_capability()
    resolver = _make_resolver(cap)
    redis = _abort_redis(abort=True)

    runtime = LeadAgentRuntime(
        resolver=resolver,
        get_workspace_type=AsyncMock(return_value="thesis"),
        redis=redis,
    )

    brief = _make_brief()
    report = await runtime.run_session(execution_id="exec-abort-1", brief=brief)

    assert report.status == "cancelled"
    assert report.errors == []


@pytest.mark.asyncio
async def test_runtime_completes_normally_without_signal():
    """When no abort signal is set, execution completes normally."""
    cap = _make_fake_capability()
    resolver = _make_resolver(cap)
    redis = _abort_redis(abort=False)

    runtime = LeadAgentRuntime(
        resolver=resolver,
        get_workspace_type=AsyncMock(return_value="thesis"),
        redis=redis,
    )

    brief = _make_brief()
    report = await runtime.run_session(execution_id="exec-no-abort-1", brief=brief)

    assert report.status == "completed"
    assert report.errors == []


@pytest.mark.asyncio
async def test_runtime_completes_normally_without_redis():
    """Without redis, abort check is skipped and execution completes normally."""
    cap = _make_fake_capability()
    resolver = _make_resolver(cap)

    runtime = LeadAgentRuntime(
        resolver=resolver,
        get_workspace_type=AsyncMock(return_value="thesis"),
        redis=None,
    )

    brief = _make_brief()
    report = await runtime.run_session(execution_id="exec-no-redis-1", brief=brief)

    assert report.status == "completed"


@pytest.mark.asyncio
async def test_execution_aborted_exception():
    """ExecutionAborted is a distinct exception class."""
    exc = ExecutionAborted("test abort")
    assert isinstance(exc, Exception)
    assert str(exc) == "test abort"
