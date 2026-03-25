"""Tests for workspace tool execution routing."""

from __future__ import annotations

import pytest

from src.agents.lead_agent.feature_bridge import BridgedChatResponse
from src.tools.builtins import workspace


@pytest.mark.asyncio
async def test_run_workspace_feature_tool_uses_shared_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def _fake_execute_workspace_feature_request(**kwargs):
        captured.update(kwargs)
        return BridgedChatResponse(
            content="task submitted",
            blocks=[{"type": "task"}],
            metadata={"orchestration": {"feature_id": kwargs["feature_id"]}},
        )

    monkeypatch.setattr(
        workspace,
        "execute_workspace_feature_request",
        _fake_execute_workspace_feature_request,
    )

    result = await workspace.run_workspace_feature_tool.coroutine(
        workspace_id="ws-1",
        thread_id="thread-1",
        user_id="user-1",
        feature_id="framework_outline",
        params={"topic": "LLM planning"},
        tool_call_id="tc-1",
    )

    assert captured == {
        "workspace_id": "ws-1",
        "thread_id": "thread-1",
        "user_id": "user-1",
        "feature_id": "framework_outline",
        "params": {"topic": "LLM planning"},
    }
    assert result.update["response_blocks"][0]["type"] == "task"
    assert (
        result.update["response_metadata"]["orchestration"]["feature_id"]
        == "framework_outline"
    )
    assert result.update["messages"][0].content == "task submitted"


@pytest.mark.asyncio
async def test_run_workspace_feature_tool_returns_explicit_error_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_execute_workspace_feature_request(**kwargs):
        return None

    monkeypatch.setattr(
        workspace,
        "execute_workspace_feature_request",
        _fake_execute_workspace_feature_request,
    )

    result = await workspace.run_workspace_feature_tool.coroutine(
        workspace_id="ws-1",
        thread_id="thread-1",
        user_id="user-1",
        feature_id="framework_outline",
        params={"topic": "LLM planning"},
        tool_call_id="tc-2",
    )

    assert "response_blocks" not in result.update
    assert "feature_execution_unavailable" in result.update["messages"][0].content
