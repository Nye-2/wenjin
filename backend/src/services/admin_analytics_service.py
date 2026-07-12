"""Admin analytics for account, credit, and workspace panels."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.provider import dataservice_client

Granularity = Literal["day", "week"]


class AdminAnalyticsService:
    """Service for admin analytics aggregation queries."""

    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self._dataservice = dataservice

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

    # ------------------------------------------------------------------
    # 1. User growth
    # ------------------------------------------------------------------
    async def user_growth(
        self, *, range_days: int, granularity: Granularity = "day"
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        since = now - timedelta(days=range_days)
        async with self._client() as client:
            growth = await client.aggregate_account_user_growth(
                since=since,
                granularity=granularity,
            )

        active_since = now - timedelta(days=1)
        async with self._client() as client:
            dau = await client.count_active_execution_users(created_since=active_since)

        active_since_w = now - timedelta(days=7)
        async with self._client() as client:
            wau = await client.count_active_execution_users(created_since=active_since_w)

        return {
            "kpis": {
                "total_users": growth.total_users,
                "new_in_range": growth.new_in_range,
                "dau": dau,
                "wau": wau,
            },
            "time_series": growth.time_series,
        }

    # ------------------------------------------------------------------
    # 2. Credit consumption
    # ------------------------------------------------------------------
    async def credit_consumption_stats(
        self, *, range_days: int, granularity: Granularity = "day"
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        since = now - timedelta(days=range_days)
        async with self._client() as client:
            stats = await client.aggregate_credit_consumption_stats(
                since=since,
                granularity=granularity,
            )
        return stats.model_dump(mode="json")

    # ------------------------------------------------------------------
    # 3. Workspace adoption
    # ------------------------------------------------------------------
    async def workspace_adoption_stats(self) -> dict[str, Any]:
        async with self._client() as client:
            stats = await client.get_admin_workspace_stats()
        by_type = [
            {
                "type": workspace_type,
                "count": int(count),
            }
            for workspace_type, count in stats.by_type.items()
        ]

        async with self._client() as client:
            account_stats = await client.get_account_admin_stats()
        total_users = account_stats.total_users

        return {
            "by_type": by_type,
            "total_workspaces": stats.total,
            "users_with_workspaces": stats.users_with_workspaces,
            "adoption_rate": (stats.users_with_workspaces / total_users) if total_users > 0 else 0.0,
        }
