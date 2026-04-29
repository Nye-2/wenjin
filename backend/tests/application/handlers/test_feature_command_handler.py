"""Tests for feature command handling from chat ingress."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.application.handlers.chat_turn_router import ChatTurnRouter
from src.application.handlers.feature_command_handler import FeatureCommandHandler
from src.application.results import GeneratedThreadReply, ThreadTurnRequest


@pytest.mark.asyncio
async def test_launch_command_calls_feature_ingress_adapter() -> None:
    request = ThreadTurnRequest(
        message="开始",
        workspace_id="ws-request",
        skill="framework-designer",
        metadata={
            "orchestration": {
                "intent": "launch",
                "feature_id": "thesis_writing",
                "params": {},
            }
        },
    )
    thread = SimpleNamespace(
        id="thread-1",
        workspace_id="ws-thread",
        workspace_type="thesis",
        skill=None,
    )
    route = ChatTurnRouter.route(request, thread)

    with patch(
        "src.application.handlers.feature_command_handler.execute_workspace_feature_request",
        new=AsyncMock(return_value=GeneratedThreadReply(content="launched")),
    ) as execute_feature:
        reply = await FeatureCommandHandler().handle(
            request=request,
            thread=thread,
            actor_id="user-1",
            route=route,
        )

    assert reply.content == "launched"
    execute_feature.assert_awaited_once_with(
        workspace_id="ws-thread",
        thread_id="thread-1",
        user_id="user-1",
        feature_id="thesis_writing",
        params={"action": "generate_outline"},
        skill_id="framework-designer",
        launch_message="开始",
        execution_session_id=None,
    )


@pytest.mark.asyncio
async def test_resume_command_reuses_execution_session() -> None:
    request = ThreadTurnRequest(
        message="这是补充信息",
        workspace_id="ws-1",
        metadata={
            "orchestration": {
                "intent": "resume",
                "execution_session_id": "exec-1",
                "params": {"topic": "LLM planning"},
            }
        },
    )
    thread = SimpleNamespace(id="thread-1", workspace_id="ws-1", skill="deep-research")
    route = ChatTurnRouter.route(request, thread)

    with patch(
        "src.application.handlers.feature_command_handler.execute_workspace_feature_request",
        new=AsyncMock(return_value=GeneratedThreadReply(content="resumed")),
    ) as execute_feature:
        reply = await FeatureCommandHandler().handle(
            request=request,
            thread=thread,
            actor_id="user-1",
            route=route,
        )

    assert reply.content == "resumed"
    assert execute_feature.await_args.kwargs["feature_id"] is None
    assert execute_feature.await_args.kwargs["execution_session_id"] == "exec-1"
    assert execute_feature.await_args.kwargs["skill_id"] == "deep-research"


@pytest.mark.asyncio
async def test_feature_proposal_returns_structured_start_card_without_launching() -> None:
    request = ThreadTurnRequest(
        message="请帮我做文献检索，主题是 LLM planning",
        workspace_id="ws-1",
    )
    thread = SimpleNamespace(
        id="thread-1",
        workspace_id="ws-1",
        workspace_type="sci",
        skill=None,
    )
    route = ChatTurnRouter.route(request, thread)

    with patch(
        "src.application.handlers.feature_command_handler.execute_workspace_feature_request",
        new=AsyncMock(),
    ) as execute_feature:
        reply = await FeatureCommandHandler().handle(
            request=request,
            thread=thread,
            actor_id="user-1",
            route=route,
        )

    assert reply.metadata["orchestration"]["mode"] == "feature_proposal"
    assert reply.metadata["orchestration"]["feature_id"] == "literature_search"
    assert reply.blocks[0]["type"] == "feature_proposal"
    assert reply.blocks[1]["type"] == "next_steps"
    assert reply.blocks[1]["data"]["items"][0]["action"] == "trigger_feature"
    assert reply.blocks[1]["data"]["items"][0]["params"]["skill"] == "deep-research"
    execute_feature.assert_not_awaited()


@pytest.mark.asyncio
async def test_launch_without_workspace_returns_warning() -> None:
    request = ThreadTurnRequest(
        message="开始",
        metadata={
            "orchestration": {
                "intent": "launch",
                "feature_id": "framework_outline",
            }
        },
    )
    thread = SimpleNamespace(id="thread-1", workspace_id=None, skill=None)
    route = ChatTurnRouter.route(request, thread)

    reply = await FeatureCommandHandler().handle(
        request=request,
        thread=thread,
        actor_id="user-1",
        route=route,
    )

    assert reply.metadata["orchestration"]["warning"] == "workspace_context_missing"
    assert reply.blocks[0]["type"] == "warning"
