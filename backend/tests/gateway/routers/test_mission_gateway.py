from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.dataservice_client.contracts.mission import (
    MissionReasoningEffort,
    MissionReviewMode,
    MissionRunPagePayload,
    MissionRunPayload,
    MissionStatus,
)
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.gateway.deps.core import get_dataservice_client
from src.gateway.routers import missions


def _user(user_id: str = "user-1") -> AccountAuthSubject:
    return AccountAuthSubject(
        id=user_id,
        email=f"{user_id}@example.com",
        name=user_id,
        role="user",
        is_active=True,
        is_superuser=False,
    )


def _run(
    *,
    user_id: str = "user-1",
    state_version: int = 4,
    last_item_seq: int = 9,
) -> MissionRunPayload:
    now = datetime(2026, 7, 11, tzinfo=UTC)
    return MissionRunPayload(
        mission_id="mission-1",
        workspace_id="workspace-1",
        thread_id="thread-1",
        user_id=user_id,
        workspace_type="sci",
        title="Research mission",
        objective="Find a defensible research gap",
        status=MissionStatus.RUNNING,
        review_mode=MissionReviewMode.BALANCED_DEFAULT,
        model_id="gpt-5.5",
        reasoning_effort=MissionReasoningEffort.XHIGH,
        pending_review_count=0,
        evidence_count=2,
        artifact_count=1,
        active_subagent_count=1,
        last_command_seq=0,
        last_applied_command_seq=0,
        lease_epoch=0,
        state_version=state_version,
        last_item_seq=last_item_seq,
        created_at=now,
        updated_at=now,
    )


def _dataservice(run: MissionRunPayload) -> SimpleNamespace:
    return SimpleNamespace(
        missions=SimpleNamespace(
            get=AsyncMock(return_value=run),
            list_workspace=AsyncMock(return_value=[run]),
            list_workspace_page=AsyncMock(
                return_value=MissionRunPagePayload(
                    items=[run],
                    next_cursor="next-history-cursor",
                )
            ),
            list_workspace_changes=AsyncMock(return_value=[run]),
        ),
        workspace_has_active_membership=AsyncMock(return_value=True),
    )


def _client(
    *,
    run: MissionRunPayload,
    runtime: SimpleNamespace,
    dataservice: SimpleNamespace | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(missions.router)
    dataservice = dataservice or _dataservice(run)
    app.dependency_overrides[get_current_user] = lambda: _user()
    app.dependency_overrides[get_dataservice_client] = lambda: dataservice
    app.dependency_overrides[missions._mission_runtime_service] = lambda: runtime
    return TestClient(app)


def test_mission_history_gateway_passes_opaque_cursor_and_returns_page() -> None:
    run = _run()
    dataservice = _dataservice(run)
    client = _client(run=run, runtime=SimpleNamespace(), dataservice=dataservice)

    response = client.get(
        "/workspaces/workspace-1/missions",
        params={"limit": 25, "cursor": "opaque-history-cursor"},
    )

    assert response.status_code == 200
    assert response.json()["next_cursor"] == "next-history-cursor"
    assert response.json()["items"][0]["mission_id"] == "mission-1"
    dataservice.missions.list_workspace_page.assert_awaited_once_with(
        workspace_id="workspace-1",
        user_id="user-1",
        limit=25,
        cursor="opaque-history-cursor",
    )


@pytest.mark.asyncio
async def test_mission_event_stream_projects_gap_hint_from_database() -> None:
    run = _run(last_item_seq=9)
    dataservice = _dataservice(run)
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    stream = missions._mission_event_stream(
        request=request,
        workspace_id=run.workspace_id,
        user_id=run.user_id,
        dataservice=dataservice,
        cursor=missions.MissionStreamCursor(
            watermark=datetime(2026, 7, 10, tzinfo=UTC),
            positions={"mission-1": (3, 4)},
        ),
        poll_seconds=0.001,
    )

    frame = await anext(stream)
    await stream.aclose()

    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line.removeprefix("data: "))
    assert payload | {"cursor": "ignored"} == {
        "type": "mission.snapshot.changed",
        "missionId": "mission-1",
        "stateVersion": 4,
        "lastItemSeq": 9,
        "replayRequired": True,
        "cursor": "ignored",
    }
    assert frame.startswith("id: ")


@pytest.mark.asyncio
async def test_mission_event_cursor_keeps_sequences_isolated_per_mission() -> None:
    first = _run(last_item_seq=100)
    second = _run(last_item_seq=2).model_copy(
        update={"mission_id": "mission-2", "updated_at": datetime(2026, 7, 11, 0, 0, 1, tzinfo=UTC)}
    )
    dataservice = _dataservice(second)
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    stream = missions._mission_event_stream(
        request=request,
        workspace_id=second.workspace_id,
        user_id=second.user_id,
        dataservice=dataservice,
        cursor=missions.MissionStreamCursor(
            watermark=datetime(2026, 7, 10, tzinfo=UTC),
            positions={first.mission_id: (first.state_version, first.last_item_seq)},
        ),
        poll_seconds=0.001,
    )
    frame = await anext(stream)
    await stream.aclose()
    payload = json.loads(next(line for line in frame.splitlines() if line.startswith("data: ")).removeprefix("data: "))
    assert payload["missionId"] == "mission-2"
    assert payload["lastItemSeq"] == 2


@pytest.mark.asyncio
async def test_mission_event_endpoint_rejects_foreign_workspace() -> None:
    dataservice = _dataservice(_run())
    dataservice.workspace_has_active_membership.return_value = False

    with pytest.raises(HTTPException) as exc:
        await missions.stream_mission_events(
            "workspace-1",
            SimpleNamespace(),
            cursor=None,
            last_event_id=None,
            current_user=_user(),
            dataservice=dataservice,
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_mission_event_endpoint_validates_last_event_id() -> None:
    dataservice = _dataservice(_run())

    with pytest.raises(HTTPException) as exc:
        await missions.stream_mission_events(
            "workspace-1",
            SimpleNamespace(),
            cursor=None,
            last_event_id="not-a-sequence",
            current_user=_user(),
            dataservice=dataservice,
        )

    assert exc.value.status_code == 400


def test_typed_mission_action_routes_through_runtime_service() -> None:
    run = _run()
    runtime = SimpleNamespace(
        cancel=AsyncMock(return_value=run),
        resume=AsyncMock(return_value=run),
        review=AsyncMock(return_value=run),
        request_commit=AsyncMock(return_value=run),
        pause=AsyncMock(return_value=run),
        set_review_mode=AsyncMock(return_value=run),
        steer=AsyncMock(return_value=run),
    )
    client = _client(run=run, runtime=runtime)

    response = client.post(
        "/missions/mission-1/actions",
        json={"action": "steer", "command_id": "command-1", "instruction": "Focus on Non-IID evidence"},
    )

    assert response.status_code == 200
    runtime.steer.assert_awaited_once_with(
        "mission-1",
        command_id="command-1",
        actor_user_id="user-1",
        input_kind="instruction",
        instruction="Focus on Non-IID evidence",
        request_id=None,
    )


def test_review_mode_action_is_a_durable_mission_command() -> None:
    run = _run()
    runtime = SimpleNamespace(
        cancel=AsyncMock(return_value=run),
        resume=AsyncMock(return_value=run),
        review=AsyncMock(return_value=run),
        request_commit=AsyncMock(return_value=run),
        pause=AsyncMock(return_value=run),
        set_review_mode=AsyncMock(return_value=run),
        steer=AsyncMock(return_value=run),
    )
    client = _client(run=run, runtime=runtime)

    response = client.post(
        "/missions/mission-1/actions",
        json={"action": "set_review_mode", "command_id": "mode-1", "review_mode": "review_all"},
    )

    assert response.status_code == 200
    runtime.set_review_mode.assert_awaited_once_with(
        "mission-1",
        command_id="mode-1",
        actor_user_id="user-1",
        review_mode=MissionReviewMode.REVIEW_ALL,
    )


def test_pause_action_enters_durable_waiting_state_through_runtime_service() -> None:
    run = _run()
    runtime = SimpleNamespace(
        pause=AsyncMock(return_value=run),
    )
    client = _client(run=run, runtime=runtime)

    response = client.post(
        "/missions/mission-1/actions",
        json={"action": "pause", "request_id": "pause-1", "reason": "Review sources first"},
    )

    assert response.status_code == 200
    runtime.pause.assert_awaited_once_with(
        "mission-1",
        request_id="pause-1",
        actor_user_id="user-1",
        reason="Review sources first",
    )


def test_mission_action_hides_foreign_mission() -> None:
    run = _run(user_id="other-user")
    runtime = SimpleNamespace(cancel=AsyncMock())
    client = _client(run=run, runtime=runtime)

    response = client.post(
        "/missions/mission-1/actions",
        json={"action": "cancel", "request_id": "cancel-1"},
    )

    assert response.status_code == 404
    runtime.cancel.assert_not_awaited()
