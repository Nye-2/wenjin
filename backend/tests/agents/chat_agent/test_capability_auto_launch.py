from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

from src.agents.middlewares.capability_auto_launch import CapabilityAutoLaunchMiddleware
from src.agents.thread_state import create_thread_state


@pytest.mark.asyncio
async def test_capability_auto_launch_calls_launch_feature_for_explicit_id(monkeypatch):
    launch = AsyncMock(
        return_value={
            "status": "launched",
            "execution_id": "exec-1",
            "feature_id": "reproducibility_audit",
        }
    )
    monkeypatch.setattr(
        "src.agents.middlewares.capability_auto_launch._invoke_launch_feature",
        launch,
    )

    state = create_thread_state(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "run reproducibility_audit. audit datasets, baselines, metrics."
                    )
                )
            ],
            "available_capabilities": [
                {
                    "id": "reproducibility_audit",
                    "display_name": "可复现性检查",
                }
            ],
        }
    )

    updates = await CapabilityAutoLaunchMiddleware().before_model(
        state,
        {
            "configurable": {
                "workspace_id": "ws-1",
                "thread_id": "thread-1",
                "user_id": "user-1",
            }
        },
    )

    assert updates["_skip_model_call"] is True
    assert updates["messages"][0].tool_calls[0]["name"] == "launch_feature"
    assert updates["messages"][0].tool_calls[0]["args"]["feature_id"] == "reproducibility_audit"
    assert updates["response_metadata"]["orchestration"]["execution_id"] == "exec-1"
    launch.assert_awaited_once()


@pytest.mark.asyncio
async def test_capability_auto_launch_ignores_non_launch_discussion(monkeypatch):
    launch = AsyncMock()
    monkeypatch.setattr(
        "src.agents.middlewares.capability_auto_launch._invoke_launch_feature",
        launch,
    )

    state = create_thread_state(
        {
            "messages": [HumanMessage(content="what is reproducibility_audit for?")],
            "available_capabilities": [
                {
                    "id": "reproducibility_audit",
                    "display_name": "可复现性检查",
                }
            ],
        }
    )

    updates = await CapabilityAutoLaunchMiddleware().before_model(
        state,
        {"configurable": {"workspace_id": "ws-1", "thread_id": "thread-1", "user_id": "user-1"}},
    )

    assert updates == {}
    launch.assert_not_awaited()


@pytest.mark.asyncio
async def test_capability_auto_launch_matches_trigger_phrase(monkeypatch):
    launch = AsyncMock(
        return_value={
            "status": "launched",
            "execution_id": "exec-sandbox",
            "feature_id": "internal_sandbox_smoke",
        }
    )
    monkeypatch.setattr(
        "src.agents.middlewares.capability_auto_launch._invoke_launch_feature",
        launch,
    )

    state = create_thread_state(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "sandbox 自检：请验证右侧 Lead Agent 可以在 Docker sandbox "
                        "中运行受控 Python 计算。"
                    )
                )
            ],
            "available_capabilities": [
                {
                    "id": "internal_sandbox_smoke",
                    "display_name": "内部实验环境自检",
                    "trigger_phrases": ["sandbox 自检", "sandbox smoke"],
                }
            ],
        }
    )

    updates = await CapabilityAutoLaunchMiddleware().before_model(
        state,
        {"configurable": {"workspace_id": "ws-1", "thread_id": "thread-1", "user_id": "user-1"}},
    )

    assert updates["_skip_model_call"] is True
    assert updates["messages"][0].tool_calls[0]["args"]["feature_id"] == "internal_sandbox_smoke"
    assert updates["response_metadata"]["orchestration"]["execution_id"] == "exec-sandbox"
    launch.assert_awaited_once()
