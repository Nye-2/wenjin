"""Tests for admin analytics aggregation."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.dataservice.domains.workspace.contracts import WorkspaceAdminStatsRecord
from src.services.admin_analytics_service import AdminAnalyticsService


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


@pytest.mark.asyncio
async def test_workspace_adoption_stats_uses_workspace_dataservice_projection() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarResult(10))
    service = AdminAnalyticsService(db)
    service._workspace.get_admin_workspace_stats = AsyncMock(
        return_value=WorkspaceAdminStatsRecord(
            total=4,
            by_type={"thesis": 3, "sci": 1},
            users_with_workspaces=2,
        )
    )

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
