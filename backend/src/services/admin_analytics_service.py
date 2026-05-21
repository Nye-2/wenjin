"""AdminAnalyticsService -- 4 aggregation methods for admin analytics panels.

All queries operate on real-time SQL via SQLAlchemy async. Callers wrap with
Redis cache decorator from admin_analytics_cache.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import User
from src.dataservice.credit_api import CreditDataService
from src.dataservice.execution_api import ExecutionDataService
from src.dataservice.workspace_api import WorkspaceDataService

Granularity = Literal["day", "week"]


def _date_trunc(granularity: Granularity, col: Any) -> Any:
    return func.date_trunc(granularity, col)


class AdminAnalyticsService:
    """Service for admin analytics aggregation queries."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
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

        bucket_col = _date_trunc(granularity, User.created_at).label("bucket")
        signups_stmt = (
            select(
                bucket_col,
                func.count().label("signups"),
            )
            .where(User.created_at >= since)
            .group_by(bucket_col)
            .order_by(bucket_col)
        )
        signups_rows = (await self.db.execute(signups_stmt)).all()

        signups_map = {
            r.bucket.isoformat(): int(r.signups) for r in signups_rows
        }
        all_buckets = sorted(signups_map.keys())

        time_series = [
            {"date": b, "signups": signups_map.get(b, 0)} for b in all_buckets
        ]

        # KPIs
        total_users = int(
            (
                await self.db.execute(select(func.count()).select_from(User))
            ).scalar()
            or 0
        )
        new_in_range = sum(signups_map.values())

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
                "total_users": total_users,
                "new_in_range": new_in_range,
                "dau": dau,
                "wau": wau,
            },
            "time_series": time_series,
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

        total_users_result = await self.db.execute(
            select(func.count()).select_from(User)
        )
        total_users = int(total_users_result.scalar() or 0)

        return {
            "by_type": by_type,
            "total_workspaces": stats.total,
            "users_with_workspaces": stats.users_with_workspaces,
            "adoption_rate": (stats.users_with_workspaces / total_users) if total_users > 0 else 0.0,
        }
