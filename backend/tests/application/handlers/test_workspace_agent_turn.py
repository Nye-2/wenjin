from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.application.errors import BadRequestError
from src.application.handlers.thread_turn_handler import (
    ThreadTurnHandler,
    _attachments_require_vision,
    _continuation_context,
    _explicit_mission_ids,
    _reply_blocks,
    _resolve_continuation_target,
    generate_thread_response,
)
from src.application.results import PreparedThreadTurn, ThreadTurnAttachment, ThreadTurnRequest
from src.dataservice_client.contracts.mission import MissionStatus
from src.models.router import InvalidRequestedModelError


def test_only_image_attachments_require_vision_capability() -> None:
    pdf = ThreadTurnAttachment(
        name="problem.pdf",
        path="uploads/problem.pdf",
        content_type="application/pdf",
    )
    mime_image = ThreadTurnAttachment(
        name="scan.bin",
        path="uploads/scan.bin",
        content_type="image/png; charset=binary",
    )
    suffix_image = ThreadTurnAttachment(
        name="diagram.webp",
        path="uploads/diagram.webp",
        content_type="application/octet-stream",
    )

    assert _attachments_require_vision((pdf,)) is False
    assert _attachments_require_vision((pdf, mime_image)) is True
    assert _attachments_require_vision((suffix_image,)) is True


def test_mission_reply_status_distinguishes_start_from_steer() -> None:
    started = _reply_blocks(
        "已开始。",
        mission_id="mission-1",
        agent_action="start_mission",
    )
    steered = _reply_blocks(
        "已更新。",
        mission_id="mission-1",
        agent_action="steer_mission",
    )
    cancelled = _reply_blocks(
        "已取消。",
        mission_id="mission-1",
        agent_action="steer_mission",
        steer_kind="cancel",
    )
    pause_requested = _reply_blocks(
        "已收到。",
        mission_id="mission-1",
        agent_action="steer_mission",
        steer_kind="pause",
    )

    assert started[0]["label"] == "研究任务已开始"
    assert started[0]["action"] == "start_mission"
    assert steered[0]["label"] == "研究要求已更新"
    assert steered[0]["action"] == "steer_mission"
    assert cancelled[0]["label"] == "研究任务已取消"
    assert pause_requested[0]["label"] == "暂停请求已提交"


def test_terminal_mission_projects_a_bounded_continuation_context() -> None:
    mission = SimpleNamespace(
        mission_id="11111111-1111-1111-1111-111111111111",
        title="校园班车三问建模论文",
        objective="完成三问建模与论文",
        status=MissionStatus.FAILED,
        mission_policy_id="math_modeling_solution",
        snapshot_json={
            "stage_acceptance": {
                "problem_understanding": {"result": "pass"},
                "question_1_model": {"result": "pass"},
                "question_1_solution_validation": {"result": "revise"},
            },
            "mission_inputs": [
                {"input_ref": f"mission-input:{'a' * 64}"},
            ],
            "last_error": {"summary": "第三问计算未完成"},
        },
        evidence_count=7,
        artifact_count=4,
    )

    projected = _continuation_context(mission)

    assert projected is not None
    assert projected.mission_id == mission.mission_id
    assert projected.passed_stage_ids == (
        "problem_understanding",
        "question_1_model",
    )
    assert projected.pinned_input_refs == (f"mission-input:{'a' * 64}",)
    assert projected.terminal_summary == "第三问计算未完成"


def test_explicit_mission_ids_only_capture_continuation_references() -> None:
    first = "11111111-1111-4111-8111-111111111111"
    second = "22222222-2222-4222-8222-222222222222"

    assert _explicit_mission_ids(f"请续接父任务 {first}") == (first,)
    assert _explicit_mission_ids(f"workspace {first}") == ()
    assert _explicit_mission_ids(f"继续任务 {first}，再重试任务 {second}") == (
        first,
        second,
    )


@pytest.mark.asyncio
async def test_explicit_continuation_target_precedes_latest_terminal_mission() -> None:
    target_id = "11111111-1111-4111-8111-111111111111"
    target = SimpleNamespace(
        mission_id=target_id,
        workspace_id="workspace-1",
        thread_id="thread-1",
        user_id="user-1",
        status=MissionStatus.FAILED,
        mission_policy_id="math_modeling_solution",
    )
    missions = SimpleNamespace(
        get=AsyncMock(return_value=target),
        get_latest_for_thread=AsyncMock(),
    )

    resolved = await _resolve_continuation_target(
        SimpleNamespace(missions=missions),  # type: ignore[arg-type]
        message=f"请严格续接父任务 {target_id}",
        workspace_id="workspace-1",
        thread_id="thread-1",
        user_id="user-1",
    )

    assert resolved is target
    missions.get.assert_awaited_once_with(target_id)
    missions.get_latest_for_thread.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_explicit_continuation_never_falls_back_to_latest() -> None:
    target_id = "11111111-1111-4111-8111-111111111111"
    missions = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                mission_id=target_id,
                workspace_id="another-workspace",
                thread_id="thread-1",
                user_id="user-1",
                status=MissionStatus.FAILED,
                mission_policy_id="math_modeling_solution",
            )
        ),
        get_latest_for_thread=AsyncMock(),
    )

    with pytest.raises(BadRequestError, match="不可续接"):
        await _resolve_continuation_target(
            SimpleNamespace(missions=missions),  # type: ignore[arg-type]
            message=f"续接任务 {target_id}",
            workspace_id="workspace-1",
            thread_id="thread-1",
            user_id="user-1",
        )

    missions.get_latest_for_thread.assert_not_called()


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
