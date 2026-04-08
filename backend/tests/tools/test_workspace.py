"""Tests for workspace tool execution routing."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

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
        state={
            "messages": [
                AIMessage(
                    content="[orchestration: feature=framework_outline, status=confirmation_required]"
                ),
                HumanMessage(content="开始吧"),
            ]
        },
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
        state={
            "messages": [
                AIMessage(
                    content="[orchestration: feature=framework_outline, status=confirmation_required]"
                ),
                HumanMessage(content="确认启动"),
            ]
        },
    )

    assert "response_blocks" not in result.update
    assert "feature_execution_unavailable" in result.update["messages"][0].content


@pytest.mark.asyncio
async def test_run_workspace_feature_tool_requires_confirmation_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _fake_execute_workspace_feature_request(**kwargs):
        nonlocal called
        called = True
        return BridgedChatResponse(content="should not run")

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
        tool_call_id="tc-3",
        state={"messages": [HumanMessage(content="请帮我生成论文框架")]},
    )

    assert called is False
    assert result.update["response_metadata"]["orchestration"]["status"] == "confirmation_required"
    assert "开始吧" in result.update["messages"][0].content


@pytest.mark.asyncio
async def test_run_workspace_feature_tool_suppresses_repeat_confirmation_in_same_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _fake_execute_workspace_feature_request(**kwargs):
        nonlocal called
        called = True
        return BridgedChatResponse(content="should not run")

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
        tool_call_id="tc-4",
        state={
            "messages": [HumanMessage(content="请帮我开始这个功能")],
            "response_metadata": {
                "orchestration": {
                    "mode": "feature_execution",
                    "feature_id": "framework_outline",
                    "status": "confirmation_required",
                }
            },
        },
    )

    assert called is False
    assert result.update["response_metadata"]["orchestration"]["status"] == "awaiting_user_confirmation"
    assert "仍在等待你的确认" in result.update["messages"][0].content
