from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.application.handlers.thread_turn_handler import ThreadTurnHandler, generate_thread_response
from src.application.results import PreparedThreadTurn, ThreadTurnRequest
from src.dataservice_client.contracts.mission import MissionStatus
from src.models.router import InvalidRequestedModelError


@pytest.mark.asyncio
async def test_requested_model_failure_is_not_silently_switched() -> None:
    workspace_service = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(workspace_type="sci"))
    )
    thread = SimpleNamespace(
        id="thread-1",
        workspace_id="workspace-1",
        model="gpt-5.6-sol",
    )
    with patch(
        "src.application.handlers.thread_turn_handler.route_chat_model",
        side_effect=InvalidRequestedModelError("unverified model"),
    ), patch("src.application.handlers.thread_turn_handler.create_chat_model") as create:
        with pytest.raises(InvalidRequestedModelError, match="unverified model"):
            await generate_thread_response(
                ThreadTurnRequest(
                    message="开始研究",
                    workspace_id="workspace-1",
                    model="unknown-model",
                ),
                thread,
                actor_id="user-1",
                user_message_id="message-1",
                workspace_service=workspace_service,
            )
    create.assert_not_called()


@pytest.mark.asyncio
async def test_chat_rollback_cancels_started_mission_before_removing_initiating_turn() -> None:
    missions = SimpleNamespace(
        get_by_idempotency_key=AsyncMock(
            return_value=SimpleNamespace(mission_id="mission-1", status=MissionStatus.RUNNING)
        ),
        cancel=AsyncMock(),
    )

    @asynccontextmanager
    async def client_context():
        yield SimpleNamespace(missions=missions)

    prepared = PreparedThreadTurn(
        request=ThreadTurnRequest(message="开始研究", workspace_id="workspace-1"),
        thread=SimpleNamespace(id="thread-1", workspace_id="workspace-1"),
        user_message_id="message-1",
    )
    with patch(
        "src.application.handlers.thread_turn_handler.dataservice_client",
        client_context,
    ):
        cancelled = await ThreadTurnHandler._cancel_started_mission(prepared)

    assert cancelled is True
    missions.get_by_idempotency_key.assert_awaited_once_with(
        workspace_id="workspace-1",
        key="mission:thread-1:message-1",
    )
    missions.cancel.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_rollback_preserves_turn_when_started_mission_is_terminal() -> None:
    missions = SimpleNamespace(
        get_by_idempotency_key=AsyncMock(
            return_value=SimpleNamespace(mission_id="mission-1", status=MissionStatus.COMPLETED)
        ),
        cancel=AsyncMock(),
    )

    @asynccontextmanager
    async def client_context():
        yield SimpleNamespace(missions=missions)

    prepared = PreparedThreadTurn(
        request=ThreadTurnRequest(message="开始研究", workspace_id="workspace-1"),
        thread=SimpleNamespace(id="thread-1", workspace_id="workspace-1"),
        user_message_id="message-1",
    )
    with patch(
        "src.application.handlers.thread_turn_handler.dataservice_client",
        client_context,
    ):
        cancelled = await ThreadTurnHandler._cancel_started_mission(prepared)

    assert cancelled is False
    missions.cancel.assert_not_awaited()
