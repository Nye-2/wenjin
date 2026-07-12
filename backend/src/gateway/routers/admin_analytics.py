"""Admin analytics endpoints."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from src.dataservice_client import AsyncDataServiceClient
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_admin
from src.gateway.deps.core import get_dataservice_client
from src.services.admin_analytics_cache import cached
from src.services.admin_analytics_service import AdminAnalyticsService
from src.services.admin_dashboard_service import AdminDashboardService

router = APIRouter(tags=["dashboard"])

Granularity = Literal["day", "week"]


def _get_service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> AdminAnalyticsService:
    return AdminAnalyticsService(dataservice=dataservice)


def _get_dashboard_service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> AdminDashboardService:
    return AdminDashboardService(dataservice=dataservice)


def _parse_range(range_str: str) -> int:
    try:
        if range_str.endswith("d"):
            days = int(range_str[:-1])
        else:
            days = int(range_str)
    except ValueError:
        return 30
    return max(1, min(days, 365))


@router.get("/dashboard/admin/analytics/user-growth")
async def user_growth(
    range: str = Query("30d"),
    granularity: Granularity = Query("day"),
    cache_bust: bool = Query(False),
    service: AdminAnalyticsService = Depends(_get_service),
    _admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any]:
    days = _parse_range(range)
    return await cached(
        cache_key=f"analytics:user-growth:{days}:{granularity}",
        fetcher=lambda: service.user_growth(range_days=days, granularity=granularity),
        cache_bust=cache_bust,
    )


@router.get("/dashboard/admin/analytics/mission-stats")
async def mission_stats(
    range: str = Query("30d"),
    granularity: Granularity = Query("day"),
    cache_bust: bool = Query(False),
    service: AdminDashboardService = Depends(_get_dashboard_service),
    _admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any]:
    days = _parse_range(range)
    return await cached(
        cache_key=f"analytics:mission-stats:{days}:{granularity}",
        fetcher=lambda: service.get_mission_stats(range_days=days, granularity=granularity),
        cache_bust=cache_bust,
    )


@router.get("/dashboard/admin/analytics/credit-consumption")
async def credit_consumption(
    range: str = Query("30d"),
    granularity: Granularity = Query("day"),
    cache_bust: bool = Query(False),
    service: AdminAnalyticsService = Depends(_get_service),
    _admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any]:
    days = _parse_range(range)
    return await cached(
        cache_key=f"analytics:credit-consumption:{days}:{granularity}",
        fetcher=lambda: service.credit_consumption_stats(range_days=days, granularity=granularity),
        cache_bust=cache_bust,
    )


@router.get("/dashboard/admin/analytics/workspace-adoption")
async def workspace_adoption(
    cache_bust: bool = Query(False),
    service: AdminAnalyticsService = Depends(_get_service),
    _admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any]:
    return await cached(
        cache_key="analytics:workspace-adoption",
        fetcher=lambda: service.workspace_adoption_stats(),
        cache_bust=cache_bust,
    )
