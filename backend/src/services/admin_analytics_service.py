"""AdminAnalyticsService -- 4 aggregation methods for admin analytics panels.

All queries operate on real-time SQL via SQLAlchemy async. Callers wrap with
Redis cache decorator from admin_analytics_cache.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.account_api import AccountDataService
from src.dataservice.credit_api import CreditDataService
from src.dataservice.execution_api import ExecutionDataService
from src.dataservice.workspace_api import WorkspaceDataService

Granularity = Literal["day", "week"]


class AdminAnalyticsService:
    """Service for admin analytics aggregation queries."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._account = AccountDataService(db, autocommit=False)
        self._credit = CreditDataService(db, autocommit=False)
        self._workspace = WorkspaceDataService(db, autocommit=False)

    # ------------------------------------------------------------------
    # 1. User growth
    # ------------------------------------------------------------------
    async def user_growth(
        self, *, range_days: int, granularity: Granularity = "day"
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        since = now - timedelta(days=range_days)
        growth = await self._account.aggregate_user_growth(
            since=since,
            granularity=granularity,
        )

        execution_data = ExecutionDataService(self.db, autocommit=False)
        active_since = now - timedelta(days=1)
        dau = await execution_data.count_active_execution_users(
            created_since=active_since,
        )

        active_since_w = now - timedelta(days=7)
        wau = await execution_data.count_active_execution_users(
            created_since=active_since_w,
        )

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
    # 2. Execution stats
    # ------------------------------------------------------------------
    async def execution_stats(
        self, *, range_days: int, granularity: Granularity = "day"
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        since = now - timedelta(days=range_days)
        return await ExecutionDataService(self.db, autocommit=False).aggregate_execution_stats(
            created_since=since,
            granularity=granularity,
        )

    # ------------------------------------------------------------------
    # 3. Credit consumption
    # ------------------------------------------------------------------
    async def credit_consumption_stats(
        self, *, range_days: int, granularity: Granularity = "day"
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        since = now - timedelta(days=range_days)
        return await self._credit.aggregate_credit_consumption_stats(
            since=since,
            granularity=granularity,
        )

    # ------------------------------------------------------------------
    # 4. Workspace adoption
    # ------------------------------------------------------------------
    async def workspace_adoption_stats(self) -> dict[str, Any]:
        stats = await self._workspace.get_admin_workspace_stats()
        by_type = [
            {
                "type": workspace_type,
                "count": int(count),
            }
            for workspace_type, count in stats.by_type.items()
        ]

        account_stats = await self._account.get_admin_stats()
        total_users = account_stats.total_users

        return {
            "by_type": by_type,
            "total_workspaces": stats.total,
            "users_with_workspaces": stats.users_with_workspaces,
            "adoption_rate": (stats.users_with_workspaces / total_users) if total_users > 0 else 0.0,
        }
