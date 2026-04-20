"""Tests for workspace tool execution routing."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.results import GeneratedThreadReply
from src.tools.builtins import workspace


@pytest.mark.asyncio
async def test_run_workspace_feature_tool_uses_shared_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def _fake_execute_workspace_feature_request(**kwargs):
        captured.update(kwargs)
        return GeneratedThreadReply(
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
        feature_id="framework_outline",
        params={"topic": "LLM planning"},
        tool_call_id="tc-1",
        config={
            "configurable": {
                "workspace_id": "ws-1",
                "thread_id": "thread-1",
                "user_id": "user-1",
            }
        },
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
        "skill_id": None,
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
        feature_id="framework_outline",
        params={"topic": "LLM planning"},
        tool_call_id="tc-2",
        config={
            "configurable": {
                "workspace_id": "ws-1",
                "thread_id": "thread-1",
                "user_id": "user-1",
            }
        },
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
        return GeneratedThreadReply(content="should not run")

    monkeypatch.setattr(
        workspace,
        "execute_workspace_feature_request",
        _fake_execute_workspace_feature_request,
    )

    result = await workspace.run_workspace_feature_tool.coroutine(
        feature_id="framework_outline",
        params={"topic": "LLM planning"},
        tool_call_id="tc-3",
        config={
            "configurable": {
                "workspace_id": "ws-1",
                "thread_id": "thread-1",
                "user_id": "user-1",
            }
        },
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
        return GeneratedThreadReply(content="should not run")

    monkeypatch.setattr(
        workspace,
        "execute_workspace_feature_request",
        _fake_execute_workspace_feature_request,
    )

    result = await workspace.run_workspace_feature_tool.coroutine(
        feature_id="framework_outline",
        params={"topic": "LLM planning"},
        tool_call_id="tc-4",
        config={
            "configurable": {
                "workspace_id": "ws-1",
                "thread_id": "thread-1",
                "user_id": "user-1",
            }
        },
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


@pytest.mark.asyncio
async def test_run_workspace_feature_tool_derives_feature_and_skill_from_current_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def _fake_execute_workspace_feature_request(**kwargs):
        captured.update(kwargs)
        return GeneratedThreadReply(content="task submitted")

    monkeypatch.setattr(
        workspace,
        "execute_workspace_feature_request",
        _fake_execute_workspace_feature_request,
    )

    result = await workspace.run_workspace_feature_tool.coroutine(
        params={"topic": "LLM planning"},
        tool_call_id="tc-5",
        config={
            "configurable": {
                "workspace_id": "ws-1",
                "thread_id": "thread-1",
                "user_id": "user-1",
            }
        },
        state={
            "workspace_type": "sci",
            "current_skill": "framework-designer",
            "messages": [
                AIMessage(
                    content="[orchestration: feature=framework_outline, status=confirmation_required]"
                ),
                HumanMessage(content="开始吧"),
            ],
        },
    )

    assert captured["feature_id"] == "framework_outline"
    assert captured["skill_id"] == "framework-designer"
    assert captured["params"] == {"topic": "LLM planning"}
    assert result.update["messages"][0].content == "task submitted"


@pytest.mark.asyncio
async def test_run_workspace_feature_tool_rejects_skill_feature_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _fake_execute_workspace_feature_request(**kwargs):
        nonlocal called
        called = True
        return GeneratedThreadReply(content="should not run")

    monkeypatch.setattr(
        workspace,
        "execute_workspace_feature_request",
        _fake_execute_workspace_feature_request,
    )

    result = await workspace.run_workspace_feature_tool.coroutine(
        feature_id="writing",
        params={"topic": "LLM planning"},
        tool_call_id="tc-6",
        config={
            "configurable": {
                "workspace_id": "ws-1",
                "thread_id": "thread-1",
                "user_id": "user-1",
            }
        },
        state={
            "workspace_type": "sci",
            "current_skill": "framework-designer",
            "messages": [HumanMessage(content="开始吧")],
        },
    )

    assert called is False
    assert result.update["response_metadata"]["orchestration"]["status"] == "skill_contract_error"
    assert "framework-designer" in result.update["messages"][0].content


@pytest.mark.asyncio
async def test_run_workspace_feature_tool_uses_orchestration_runtime_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def _fake_execute_workspace_feature_request(**kwargs):
        captured.update(kwargs)
        return GeneratedThreadReply(content="launched")

    monkeypatch.setattr(
        workspace,
        "execute_workspace_feature_request",
        _fake_execute_workspace_feature_request,
    )

    result = await workspace.run_workspace_feature_tool.coroutine(
        params={"topic": "override"},
        tool_call_id="",
        config={
            "configurable": {
                "workspace_id": "ws-1",
                "thread_id": "thread-1",
                "user_id": "user-1",
                "tool_call_id": "cfg-tool-call-1",
                "orchestration_intent": "launch",
                "orchestration_feature_id": "framework_outline",
                "orchestration_params": {
                    "topic": "runtime topic",
                    "language": "zh",
                },
            }
        },
        state={"messages": [HumanMessage(content="直接执行")]},
    )

    assert captured == {
        "workspace_id": "ws-1",
        "thread_id": "thread-1",
        "user_id": "user-1",
        "feature_id": "framework_outline",
        "params": {"topic": "override", "language": "zh"},
        "skill_id": None,
    }
    assert result.update["messages"][0].content == "launched"
    assert result.update["messages"][0].tool_call_id == "cfg-tool-call-1"


@pytest.mark.asyncio
async def test_run_workspace_feature_tool_falls_back_to_state_runtime_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def _fake_execute_workspace_feature_request(**kwargs):
        captured.update(kwargs)
        return GeneratedThreadReply(content="launched")

    monkeypatch.setattr(
        workspace,
        "execute_workspace_feature_request",
        _fake_execute_workspace_feature_request,
    )

    result = await workspace.run_workspace_feature_tool.coroutine(
        feature_id="framework_outline",
        params={"topic": "LLM planning"},
        tool_call_id="tc-state-fallback",
        config={"configurable": {"orchestration_intent": "launch"}},
        state={
            "workspace_id": "ws-state",
            "thread_id": "thread-state",
            "user_id": "user-state",
            "messages": [HumanMessage(content="执行")],
        },
    )

    assert captured["workspace_id"] == "ws-state"
    assert captured["thread_id"] == "thread-state"
    assert captured["user_id"] == "user-state"
    assert result.update["messages"][0].content == "launched"


@pytest.mark.asyncio
async def test_run_workspace_feature_tool_uses_non_empty_tool_call_id_for_errors() -> None:
    result = await workspace.run_workspace_feature_tool.coroutine(
        feature_id="framework_outline",
        params={"topic": "LLM planning"},
        tool_call_id="",
        config=None,
        state=None,
    )

    message = result.update["messages"][0]
    assert message.tool_call_id == "run_workspace_feature"
    assert result.update["response_metadata"]["orchestration"]["status"] == "runtime_context_missing"
