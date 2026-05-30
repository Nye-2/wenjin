"""Tests for user dashboard aggregation."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

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
        self.status_counts: dict[str, int] = {}

    async def get_account_user(self, user_id: str) -> AccountUserPayload | None:
        return self.user if user_id == self.user.id else None

    async def get_workspace_stats_for_member(self, user_id: str) -> WorkspaceStatsPayload:
        return self.workspace_stats

    async def count_executions_by_status(self, *, user_id: str | None = None) -> dict[str, int]:
        return self.status_counts

@pytest.mark.asyncio
async def test_get_dashboard_includes_thread_credit_status() -> None:
    db = AsyncMock()
    fake_client = FakeDashboardDataServiceClient()
    service = UserDashboardService(db, dataservice=fake_client)
    service._get_workspace_stats = AsyncMock(return_value={"total": 1, "by_type": {"thesis": 1}, "created_last_7d": 0})
    service._get_task_stats = AsyncMock(
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

    with patch(
        "src.services.user_dashboard_service.CreditService.get_thread_billing_policy",
        return_value=SimpleNamespace(enabled=True, free_tokens=100000, tokens_per_credit=10000),
    ), patch(
        "src.services.user_dashboard_service.CreditService.get_consumed_thread_tokens",
        AsyncMock(return_value=120000),
    ), patch(
        "src.services.user_dashboard_service.CreditService.can_start_thread_turn",
        AsyncMock(return_value=False),
    ) as can_start_thread_turn:
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
    db = AsyncMock()
    fake_client = FakeDashboardDataServiceClient()
    fake_client.workspace_stats = WorkspaceStatsPayload(
        total=2,
        by_type={"thesis": 1, "sci": 1},
        created_last_7d=1,
    )
    service = UserDashboardService(db, dataservice=fake_client)

    stats = await service._get_workspace_stats("user-1")

    assert stats == {
        "total": 2,
        "by_type": {"thesis": 1, "sci": 1},
        "created_last_7d": 1,
    }
