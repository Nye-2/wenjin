"""Tests for user dashboard aggregation."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.account import AccountUserPayload
from src.dataservice_client.contracts.workspace import WorkspaceStatsPayload
from src.services.user_dashboard_service import UserDashboardService


class FakeDashboardDataServiceClient:
    def __init__(self) -> None:
        self.user = AccountUserPayload(
            id="user-1",
            email="user-1@example.com",
            name="User 1",
            role="user",
            is_active=True,
            is_superuser=False,
            credits=-2,
            total_credits_earned=100,
            total_credits_spent=102,
            created_at=datetime(2026, 3, 26, tzinfo=UTC),
            last_login=None,
        )
        self.workspace_stats = WorkspaceStatsPayload(
            total=0,
            by_type={},
            created_last_7d=0,
        )

    async def get_account_user(self, user_id: str) -> AccountUserPayload | None:
        return self.user if user_id == self.user.id else None

    async def get_workspace_stats_for_member(self, user_id: str) -> WorkspaceStatsPayload:
        return self.workspace_stats


@pytest.mark.asyncio
async def test_get_dashboard_includes_thread_credit_status() -> None:
    fake_client = FakeDashboardDataServiceClient()
    service = UserDashboardService(dataservice=fake_client)
    service._get_workspace_stats = AsyncMock(return_value={"total": 1, "by_type": {"thesis": 1}, "created_last_7d": 0})
    service._get_mission_stats = AsyncMock(
        return_value=(
            {
                "total": 0,
                "success": 0,
                "running": 0,
                "failed": 0,
                "pending": 0,
                "cancelled": 0,
                "completion_rate": 0.0,
            },
            [],
        )
    )

    with (
        patch(
            "src.services.user_dashboard_service.CreditService.get_thread_billing_policy",
            return_value=SimpleNamespace(enabled=True, free_tokens=100000, tokens_per_credit=10000),
        ),
        patch(
            "src.services.user_dashboard_service.CreditService.get_consumed_thread_tokens",
            AsyncMock(return_value=120000),
        ),
        patch(
            "src.services.user_dashboard_service.CreditService.can_start_thread_turn",
            AsyncMock(return_value=False),
        ) as can_start_thread_turn,
    ):
        payload = await service.get_dashboard("user-1")

    assert payload["credits"]["thread"] == {
        "enabled": True,
        "can_start_thread": False,
        "overdraft_credits": 2,
        "billing_unit": "credits",
        "pricing": "usage_based",
    }
    assert "token_usage" not in payload
    assert "tokens_per_credit" not in payload["credits"]["thread"]
    assert "free_tokens" not in payload["credits"]["thread"]
    can_start_thread_turn.assert_not_called()


@pytest.mark.asyncio
async def test_get_workspace_stats_uses_dataservice_projection() -> None:
    fake_client = FakeDashboardDataServiceClient()
    fake_client.workspace_stats = WorkspaceStatsPayload(
        total=2,
        by_type={"thesis": 1, "sci": 1},
        created_last_7d=1,
    )
    service = UserDashboardService(dataservice=fake_client)

    stats = await service._get_workspace_stats("user-1")

    assert stats == {
        "total": 2,
        "by_type": {"thesis": 1, "sci": 1},
        "created_last_7d": 1,
    }


def _mission_payload(
    mission_id: str,
    *,
    workspace_id: str,
    status: str,
    updated_at: datetime,
) -> dict:
    completed_at = updated_at if status in {"completed", "failed", "cancelled"} else None
    return {
        "mission_id": mission_id,
        "parent_mission_id": None,
        "workspace_id": workspace_id,
        "thread_id": None,
        "user_id": "user-1",
        "workspace_type": "sci",
        "mission_policy_id": "sci.research",
        "title": f"Mission {mission_id}",
        "objective": f"Objective {mission_id}",
        "status": status,
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
        "mission_idempotency_key": None,
        "last_command_seq": 0,
        "last_applied_command_seq": 0,
        "next_wakeup_at": None,
        "lease_owner": None,
        "lease_epoch": 0,
        "lease_expires_at": None,
        "dispatch_owner": None,
        "dispatch_epoch": 0,
        "dispatch_expires_at": None,
        "state_version": 0,
        "last_item_seq": 0,
        "created_at": updated_at.isoformat(),
        "updated_at": updated_at.isoformat(),
        "started_at": None,
        "completed_at": completed_at.isoformat() if completed_at else None,
    }


@pytest.mark.asyncio
async def test_mission_stats_use_real_dataservice_client_surface_and_pagination() -> None:
    older = datetime(2026, 3, 25, tzinfo=UTC)
    newer = datetime(2026, 3, 26, tzinfo=UTC)
    mission_requests: list[tuple[str, str | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/internal/v1/workspaces":
            assert request.url.params["member_user_id"] == "user-1"
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": [
                        {
                            "id": "workspace-1",
                            "created_by_user_id": "user-1",
                            "name": "Workspace 1",
                            "workspace_type": "sci",
                        },
                        {
                            "id": "workspace-2",
                            "created_by_user_id": "user-1",
                            "name": "Workspace 2",
                            "workspace_type": "sci",
                        },
                    ],
                },
            )

        workspace_id = request.url.path.split("/")[4]
        cursor = request.url.params.get("cursor")
        mission_requests.append((workspace_id, cursor))
        assert request.url.params["user_id"] == "user-1"
        assert request.url.params["limit"] == "100"

        pages = {
            ("workspace-1", None): {
                "items": [
                    _mission_payload("completed", workspace_id="workspace-1", status="completed", updated_at=older),
                    _mission_payload("planning", workspace_id="workspace-1", status="planning", updated_at=older),
                    _mission_payload("running", workspace_id="workspace-1", status="running", updated_at=older),
                ],
                "next_cursor": "workspace-1-next",
            },
            ("workspace-1", "workspace-1-next"): {
                "items": [_mission_payload("failed", workspace_id="workspace-1", status="failed", updated_at=older)],
                "next_cursor": None,
            },
            ("workspace-2", None): {
                "items": [
                    _mission_payload("waiting", workspace_id="workspace-2", status="waiting", updated_at=newer),
                    _mission_payload("created", workspace_id="workspace-2", status="created", updated_at=older),
                    _mission_payload("cancelled", workspace_id="workspace-2", status="cancelled", updated_at=older),
                ],
                "next_cursor": None,
            },
        }
        return httpx.Response(200, json={"status": "ok", "data": pages[(workspace_id, cursor)]})

    async with AsyncDataServiceClient(
        base_url="http://dataservice",
        internal_token="secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        stats, recent = await UserDashboardService(dataservice=client)._get_mission_stats("user-1")

    assert mission_requests == [
        ("workspace-1", None),
        ("workspace-1", "workspace-1-next"),
        ("workspace-2", None),
    ]
    assert stats == {
        "total": 7,
        "success": 1,
        "running": 3,
        "failed": 1,
        "pending": 1,
        "cancelled": 1,
        "completion_rate": 0.3333,
    }
    assert recent[0] == {
        "id": "waiting",
        "task_type": "Mission waiting",
        "status": "waiting",
        "progress": 0,
        "message": "Objective waiting",
        "created_at": newer.isoformat(),
        "completed_at": None,
    }
