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


def _mission_view_payload() -> dict:
    payload = _mission_payload()
    internal_fields = {
        "user_id",
        "mission_policy_id",
        "snapshot_json",
        "runtime_context_json",
        "context_checkpoint_ref",
        "mission_idempotency_key",
        "last_command_seq",
        "last_applied_command_seq",
        "next_wakeup_at",
        "lease_owner",
        "lease_epoch",
        "lease_expires_at",
    }
    return {key: value for key, value in payload.items() if key not in internal_fields}


def _mission_item_payload(seq: int) -> dict:
    return {
        "id": f"item-{seq}",
        "mission_id": "mission-1",
        "seq": seq,
        "item_type": "artifact",
        "phase": "completed",
        "payload_json": {},
        "created_at": datetime.now(UTC).isoformat(),
    }


def _mission_review_item_payload(review_item_id: str) -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "review_item_id": review_item_id,
        "mission_id": "mission-1",
        "source_item_seq": None,
        "output_key": review_item_id,
        "target_kind": "memory",
        "target_room": "memory",
        "target_ref": review_item_id,
        "title": "Review candidate",
        "risk_level": "low",
        "status": "pending",
        "preview_json": {"body": "candidate"},
        "requires_explicit_review": False,
        "batch_acceptable": True,
        "suggested_selected": True,
        "created_at": now,
        "updated_at": now,
    }


def _mission_commit_payload(commit_id: str) -> dict:
    return {
        "commit_id": commit_id,
        "mission_id": "mission-1",
        "review_item_id": "review-1",
        "commit_key": commit_id,
        "status": "pending",
        "actor_user_id": "user-1",
        "targets_json": {},
        "attempt_count": 0,
        "created_at": datetime.now(UTC).isoformat(),
    }


@pytest.mark.asyncio
async def test_root_client_exposes_composed_mission_domain_and_typed_create() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/v1/mission-admissions"
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
        result = await client.missions.admit(
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
            "data": {"items": [_mission_view_payload()], "next_cursor": "next-token"},
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
            "data": {"items": [_mission_view_payload()], "next_cursor": None},
        }

    runs = await MissionDataServiceClient(request).list_workspace(
        workspace_id="workspace-1",
        limit=5,
    )

    assert [run.mission_id for run in runs] == ["mission-1"]


@pytest.mark.asyncio
async def test_latest_thread_mission_client_includes_terminal_context() -> None:
    async def request(method: str, path: str, **kwargs):
        assert method == "GET"
        assert path == (
            "/internal/v1/workspaces/workspace-1/threads/thread-1/latest-mission"
        )
        assert kwargs["params"] == {"user_id": "user-1"}
        mission = _mission_payload()
        mission["status"] = "failed"
        return {"status": "ok", "data": mission}

    latest = await MissionDataServiceClient(request).get_latest_for_thread(
        workspace_id="workspace-1",
        thread_id="thread-1",
        user_id="user-1",
    )

    assert latest is not None
    assert latest.status.value == "failed"


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


@pytest.mark.asyncio
async def test_model_call_state_client_uses_typed_projection_route() -> None:
    now = datetime.now(UTC).isoformat()
    started = {
        "id": "item-model-started",
        "mission_id": "mission-1",
        "seq": 4,
        "item_type": "model_call_started",
        "operation_id": "model-call:workspace:1",
        "phase": "started",
        "producer": "workspace_agent",
        "payload_json": {
            "model_call_id": "model-call:workspace:1",
            "model_id": "gpt-5.6-sol",
            "turn": 1,
            "attempt": 1,
        },
        "created_at": now,
    }
    terminal = {
        **started,
        "id": "item-model-terminal",
        "seq": 5,
        "item_type": "model_call_terminal",
        "phase": "failed",
        "payload_json": {
            **started["payload_json"],
            "outcome": "unresolved",
            "detail": "Provider usage could not be confirmed",
        },
    }

    async def request(method: str, path: str, **kwargs):
        assert method == "GET"
        assert path == "/internal/v1/missions/mission-1/model-calls"
        assert kwargs == {}
        return {
            "status": "ok",
            "data": [
                {
                    "state": "unresolved",
                    "started": started,
                    "terminal": terminal,
                }
            ],
        }

    states = await MissionDataServiceClient(request).list_model_call_states(
        "mission-1"
    )

    assert len(states) == 1
    assert states[0].state.value == "unresolved"
    assert states[0].terminal is not None
    assert states[0].terminal.seq == 5


@pytest.mark.asyncio
async def test_item_seq_batch_client_uses_one_typed_request() -> None:
    async def request(method: str, path: str, **kwargs):
        assert method == "POST"
        assert path == "/internal/v1/missions/mission-1/items/by-seqs"
        assert kwargs["json"] == {"seqs": [3, 8]}
        return {
            "status": "ok",
            "data": [_mission_item_payload(3), _mission_item_payload(8)],
        }

    items = await MissionDataServiceClient(request).list_items_by_seqs(
        "mission-1",
        seqs=(3, 8),
    )

    assert [item.seq for item in items] == [3, 8]


@pytest.mark.asyncio
async def test_item_page_client_keeps_pagination_bounded() -> None:
    async def request(method: str, path: str, **kwargs):
        assert method == "GET"
        assert path == "/internal/v1/missions/mission-1/items"
        assert kwargs["params"] == {
            "after_seq": 4,
            "limit": 2,
            "item_type": "artifact",
            "operation_id": None,
        }
        return {
            "status": "ok",
            "data": {
                "items": [_mission_item_payload(5), _mission_item_payload(6)],
                "page": {"total": 8, "returned": 2, "next_cursor": 6},
            },
        }

    page = await MissionDataServiceClient(request).list_items_page(
        "mission-1",
        after_seq=4,
        limit=2,
        item_type="artifact",
    )

    assert [item.seq for item in page.items] == [5, 6]
    assert page.page.next_cursor == 6


@pytest.mark.asyncio
async def test_review_and_commit_clients_use_opaque_page_cursors() -> None:
    calls: list[str] = []

    async def request(method: str, path: str, **kwargs):
        assert method == "GET"
        calls.append(path)
        if path.endswith("/review-items"):
            assert kwargs["params"] == {
                "status": ["pending"],
                "limit": 20,
                "cursor": "review-cursor",
            }
            return {
                "status": "ok",
                "data": {
                    "items": [_mission_review_item_payload("review-1")],
                    "page": {
                        "total": 1,
                        "returned": 1,
                        "next_cursor": None,
                    },
                },
            }
        assert path.endswith("/commits")
        assert kwargs["params"] == {"limit": 20, "cursor": "commit-cursor"}
        return {
            "status": "ok",
            "data": {
                "items": [_mission_commit_payload("commit-1")],
                "page": {"total": 1, "returned": 1, "next_cursor": None},
            },
        }

    client = MissionDataServiceClient(request)
    reviews = await client.list_review_items_page(
        "mission-1",
        status=["pending"],
        limit=20,
        cursor="review-cursor",
    )
    commits = await client.list_commits_page(
        "mission-1",
        limit=20,
        cursor="commit-cursor",
    )

    assert [item.review_item_id for item in reviews.items] == ["review-1"]
    assert [item.commit_id for item in commits.items] == ["commit-1"]
    assert calls == [
        "/internal/v1/missions/mission-1/review-items",
        "/internal/v1/missions/mission-1/commits",
    ]


@pytest.mark.asyncio
async def test_artifact_client_forwards_equal_seq_tiebreaker() -> None:
    async def request(method: str, path: str, **kwargs):
        assert method == "GET"
        assert path == "/internal/v1/missions/mission-1/artifacts"
        assert kwargs["params"] == {
            "after_seq": 7,
            "after_review_item_id": "review-7",
            "limit": 5,
        }
        return {
            "status": "ok",
            "data": {
                "items": [],
                "page": {
                    "total": 7,
                    "returned": 0,
                    "next_cursor": None,
                    "next_tiebreaker": None,
                },
            },
        }

    page = await MissionDataServiceClient(request).list_artifact_projection(
        "mission-1",
        after_seq=7,
        after_review_item_id="review-7",
        limit=5,
    )

    assert page is not None
    assert page.page.total == 7


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
