"""Wire-shape tests for the composed Mission DataService client."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.mission import (
    MissionCreatePayload,
    MissionUserCommandPayload,
)
from src.dataservice_client.mission_client import MissionDataServiceClient


def _mission_payload() -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "mission_id": "mission-1",
        "parent_mission_id": None,
        "workspace_id": "workspace-1",
        "thread_id": "thread-1",
        "user_id": "user-1",
        "workspace_type": "sci",
        "mission_policy_id": "sci.research",
        "title": "Research gap",
        "objective": "Find a gap",
        "status": "created",
        "review_mode": "balanced_default",
        "active_stage_id": None,
        "model_id": "gpt-5.6-sol",
        "reasoning_effort": "xhigh",
        "snapshot_json": {},
        "runtime_context_json": {},
        "context_checkpoint_ref": None,
        "pending_review_count": 0,
        "evidence_count": 0,
        "artifact_count": 0,
        "active_subagent_count": 0,
        "mission_idempotency_key": "mission-create-1",
        "last_command_seq": 0,
        "last_applied_command_seq": 0,
        "next_wakeup_at": now,
        "lease_owner": None,
        "lease_epoch": 0,
        "lease_expires_at": None,
        "state_version": 0,
        "last_item_seq": 0,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "completed_at": None,
    }


@pytest.mark.asyncio
async def test_root_client_exposes_composed_mission_domain_and_typed_create() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/v1/missions"
        body = json.loads(request.content)
        assert body["model_id"] == "gpt-5.6-sol"
        assert body["reasoning_effort"] == "xhigh"
        assert "execution_id" not in body
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "data": {"mission": _mission_payload(), "created": True},
            },
        )

    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        assert isinstance(client.missions, MissionDataServiceClient)
        result = await client.missions.create(
            MissionCreatePayload(
                workspace_id="workspace-1",
                thread_id="thread-1",
                user_id="user-1",
                workspace_type="sci",
                mission_policy_id="sci.research",
                title="Research gap",
                objective="Find a gap",
                model_id="gpt-5.6-sol",
                reasoning_effort="xhigh",
                mission_idempotency_key="mission-create-1",
            )
        )

    assert result.created is True
    assert result.mission.status == "created"


@pytest.mark.asyncio
async def test_mission_history_client_uses_single_opaque_cursor() -> None:
    cursor = "opaque-cursor-token"

    async def request(method: str, path: str, **kwargs):
        assert method == "GET"
        assert path == "/internal/v1/workspaces/workspace-1/missions"
        assert kwargs["params"] == {
            "user_id": "user-1",
            "status": None,
            "limit": 25,
            "cursor": cursor,
        }
        assert "before_updated_at" not in kwargs["params"]
        return {
            "status": "ok",
            "data": {"items": [_mission_payload()], "next_cursor": "next-token"},
        }

    page = await MissionDataServiceClient(request).list_workspace_page(
        workspace_id="workspace-1",
        user_id="user-1",
        limit=25,
        cursor=cursor,
    )

    assert [item.mission_id for item in page.items] == ["mission-1"]
    assert page.next_cursor == "next-token"


@pytest.mark.asyncio
async def test_recent_workspace_missions_projects_items_from_page_contract() -> None:
    async def request(method: str, path: str, **kwargs):
        assert method == "GET"
        assert path == "/internal/v1/workspaces/workspace-1/missions"
        assert kwargs["params"]["cursor"] is None
        return {
            "status": "ok",
            "data": {"items": [_mission_payload()], "next_cursor": None},
        }

    runs = await MissionDataServiceClient(request).list_workspace(
        workspace_id="workspace-1",
        limit=5,
    )

    assert [run.mission_id for run in runs] == ["mission-1"]


@pytest.mark.asyncio
async def test_command_client_uses_mission_route_and_stable_command_id() -> None:
    async def request(method: str, path: str, **kwargs):
        assert method == "POST"
        assert path == "/internal/v1/missions/mission-1/commands"
        assert kwargs["json"]["command_id"] == "command-1"
        mission = _mission_payload()
        mission.update({"state_version": 1, "last_item_seq": 1, "last_command_seq": 1})
        return {
            "status": "ok",
            "data": {
                "mission": mission,
                "items": [
                    {
                        "id": "item-1",
                        "mission_id": "mission-1",
                        "seq": 1,
                        "item_type": "command_received",
                        "operation_id": "command-1",
                        "phase": "completed",
                        "payload_json": {"command_type": "steer"},
                        "created_at": mission["created_at"],
                    }
                ],
            },
        }

    client = MissionDataServiceClient(request)
    result = await client.append_command(
        "mission-1",
        MissionUserCommandPayload(
            command_id="command-1",
            command_type="steer",
        ),
    )
    assert result.items[0].operation_id == "command-1"


def test_mission_contract_rejects_execution_record_fields() -> None:
    with pytest.raises(ValidationError, match="execution_id"):
        MissionCreatePayload(
            workspace_id="workspace-1",
            user_id="user-1",
            workspace_type="sci",
            title="Research gap",
            objective="Find a gap",
            model_id="gpt-5.6-sol",
            reasoning_effort="xhigh",
            execution_id="execution-1",  # type: ignore[call-arg]
        )
