"""Tests for admin analytics aggregation."""

from __future__ import annotations

import pytest

from src.dataservice_client.contracts.account import AccountAdminStatsPayload
from src.dataservice_client.contracts.workspace import WorkspaceAdminStatsPayload
from src.services.admin_analytics_service import AdminAnalyticsService


class FakeAdminAnalyticsClient:
    def __init__(self) -> None:
        self.workspace_stats = WorkspaceAdminStatsPayload(
            total=4,
            by_type={"thesis": 3, "sci": 1},
            users_with_workspaces=2,
        )
        self.account_stats = AccountAdminStatsPayload(
            total_users=10,
            active_users=10,
            admin_users=1,
        )

    async def get_admin_workspace_stats(self) -> WorkspaceAdminStatsPayload:
        return self.workspace_stats

    async def get_account_admin_stats(self) -> AccountAdminStatsPayload:
        return self.account_stats


@pytest.mark.asyncio
async def test_workspace_adoption_stats_uses_workspace_dataservice_projection() -> None:
    service = AdminAnalyticsService(dataservice=FakeAdminAnalyticsClient())

    stats = await service.workspace_adoption_stats()

    assert stats == {
        "by_type": [
            {"type": "thesis", "count": 3},
            {"type": "sci", "count": 1},
        ],
        "total_workspaces": 4,
        "users_with_workspaces": 2,
        "adoption_rate": 0.2,
    }
