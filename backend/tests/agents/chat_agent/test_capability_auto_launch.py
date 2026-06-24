from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

from src.agents.middlewares.capability_auto_launch import CapabilityAutoLaunchMiddleware
from src.agents.thread_state import create_thread_state


@pytest.mark.asyncio
async def test_capability_auto_launch_requires_explicit_runtime_feature_id(monkeypatch):
    launch = AsyncMock()
    monkeypatch.setattr(
        "src.agents.middlewares.capability_auto_launch._invoke_launch_feature",
        launch,
    )

    state = create_thread_state(
        {
            "messages": [HumanMessage(content="run reproducibility_audit")],
            "available_capabilities": [{"id": "reproducibility_audit", "display_name": "可复现性检查"}],
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

    assert updates == {}
    launch.assert_not_awaited()


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
async def test_capability_auto_launch_does_not_launch_hidden_trigger_phrase(monkeypatch):
    launch = AsyncMock()
    monkeypatch.setattr(
        "src.agents.middlewares.capability_auto_launch._invoke_launch_feature",
        launch,
    )

    state = create_thread_state(
        {
            "messages": [HumanMessage(content="sandbox 自检")],
            "available_capabilities": [
                {
                    "id": "internal_sandbox_smoke",
                    "display_name": "内部实验环境自检",
                    "trigger_phrases": ["sandbox 自检"],
                    "entry_tier": "hidden",
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


@pytest.mark.parametrize("display", [{"entry_tier": "hidden"}, {"tier": "hidden"}])
@pytest.mark.asyncio
async def test_capability_auto_launch_blocks_explicit_hidden_display_tier(
    monkeypatch,
    display,
):
    launch = AsyncMock(
        return_value={"status": "launched", "execution_id": "exec-hidden", "feature_id": "internal_sandbox_smoke"}
    )
    monkeypatch.setattr(
        "src.agents.middlewares.capability_auto_launch._invoke_launch_feature",
        launch,
    )

    state = create_thread_state(
        {
            "messages": [HumanMessage(content="请开始这个入口任务")],
            "available_capabilities": [
                {
                    "id": "internal_sandbox_smoke",
                    "display_name": "内部实验环境自检",
                    "tier": "primary",
                    "display": display,
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
                "launch_feature_id": "internal_sandbox_smoke",
            }
        },
    )

    assert updates == {}
    launch.assert_not_awaited()


@pytest.mark.asyncio
async def test_capability_auto_launch_blocks_explicit_hidden_definition_display_tier(
    monkeypatch,
):
    launch = AsyncMock(
        return_value={"status": "launched", "execution_id": "exec-hidden", "feature_id": "internal_sandbox_smoke"}
    )
    monkeypatch.setattr(
        "src.agents.middlewares.capability_auto_launch._invoke_launch_feature",
        launch,
    )

    state = create_thread_state(
        {
            "messages": [HumanMessage(content="请开始这个入口任务")],
            "available_capabilities": [
                {
                    "id": "internal_sandbox_smoke",
                    "display_name": "内部实验环境自检",
                    "tier": "primary",
                    "definition_json": {"display": {"entry_tier": "hidden"}},
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
                "launch_feature_id": "internal_sandbox_smoke",
            }
        },
    )

    assert updates == {}
    launch.assert_not_awaited()


@pytest.mark.asyncio
async def test_capability_auto_launch_allows_explicit_runtime_feature_id(monkeypatch):
    launch = AsyncMock(
        return_value={"status": "launched", "execution_id": "exec-1", "feature_id": "reproducibility_audit"}
    )
    monkeypatch.setattr(
        "src.agents.middlewares.capability_auto_launch._invoke_launch_feature",
        launch,
    )
    state = create_thread_state(
        {
            "messages": [HumanMessage(content="请开始这个入口任务")],
            "available_capabilities": [{"id": "reproducibility_audit", "display_name": "可复现性检查"}],
        }
    )

    updates = await CapabilityAutoLaunchMiddleware().before_model(
        state,
        {
            "configurable": {
                "workspace_id": "ws-1",
                "thread_id": "thread-1",
                "user_id": "user-1",
                "launch_feature_id": "reproducibility_audit",
            }
        },
    )

    assert updates["_skip_model_call"] is True
    assert updates["response_metadata"]["orchestration"]["execution_id"] == "exec-1"
    launch.assert_awaited_once()
