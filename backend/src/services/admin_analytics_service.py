"""AdminAnalyticsService -- 4 aggregation methods for admin analytics panels.

All queries operate on real-time SQL via SQLAlchemy async. Callers wrap with
Redis cache decorator from admin_analytics_cache.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import (
    CreditTransaction,
    CreditTransactionType,
    User,
    Workspace,
)
from src.dataservice.execution_api import ExecutionDataService

Granularity = Literal["day", "week"]


def _date_trunc(granularity: Granularity, col: Any) -> Any:
    return func.date_trunc(granularity, col)


class AdminAnalyticsService:
    """Service for admin analytics aggregation queries."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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

        inflow_types = {
            CreditTransactionType.ADMIN_GRANT,
            CreditTransactionType.REGISTRATION_BONUS,
            CreditTransactionType.REFUND,
        }

        bucket_col = _date_trunc(granularity, CreditTransaction.created_at).label(
            "bucket"
        )
        ttype_col = CreditTransaction.transaction_type
        stmt = (
            select(
                bucket_col,
                ttype_col.label("ttype"),
                func.sum(CreditTransaction.amount).label("total"),
            )
            .where(CreditTransaction.created_at >= since)
            .group_by(bucket_col, ttype_col)
            .order_by(bucket_col)
        )
        rows = (await self.db.execute(stmt)).all()

        series_by_bucket: dict[str, dict[str, Any]] = {}
        for r in rows:
            bucket = r.bucket.isoformat()
            ttype = (
                r.ttype if isinstance(r.ttype, str) else r.ttype.value
            )
            amount = int(r.total)
            series_by_bucket.setdefault(
                bucket, {"date": bucket, "inflow": 0, "outflow": 0, "by_type": {}}
            )
            try:
                ttype_enum = CreditTransactionType(ttype)
            except ValueError:
                continue
            if ttype_enum in inflow_types:
                series_by_bucket[bucket]["inflow"] += amount
            else:
                series_by_bucket[bucket]["outflow"] += abs(amount)
            series_by_bucket[bucket]["by_type"][ttype] = amount

        credit_series = [series_by_bucket[k] for k in sorted(series_by_bucket)]

        # KPIs
        kpis_result = await self.db.execute(
            select(
                func.coalesce(func.sum(User.total_credits_earned), 0).label(
                    "issued"
                ),
                func.coalesce(func.sum(User.total_credits_spent), 0).label(
                    "spent"
                ),
                func.coalesce(func.sum(User.credits), 0).label("pool"),
            )
        )
        kpi_row = kpis_result.one()

        return {
            "kpis": {
                "total_issued": int(kpi_row.issued),
                "total_spent": int(kpi_row.spent),
                "current_pool": int(kpi_row.pool),
            },
            "credit_series": credit_series,
        }

    # ------------------------------------------------------------------
    # 4. Workspace adoption
    # ------------------------------------------------------------------
    async def workspace_adoption_stats(self) -> dict[str, Any]:
        ws_result = await self.db.execute(
            select(Workspace.type, func.count()).group_by(Workspace.type)
        )
        by_type = [
            {
                "type": (
                    t if isinstance(t, str) else t.value
                ),
                "count": int(c),
            }
            for t, c in ws_result.all()
        ]

        total_ws = sum(item["count"] for item in by_type)

        # Users with at least one workspace
        users_with_ws = await self.db.execute(
            select(func.count(distinct(Workspace.user_id)))
        )
        users_count = int(users_with_ws.scalar() or 0)

        total_users_result = await self.db.execute(
            select(func.count()).select_from(User)
        )
        total_users = int(total_users_result.scalar() or 0)

        return {
            "by_type": by_type,
            "total_workspaces": total_ws,
            "users_with_workspaces": users_count,
            "adoption_rate": (users_count / total_users) if total_users > 0 else 0.0,
        }
