from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.gateway.auth_dependencies import AccountAuthSubject
from src.gateway.routers.admin_analytics import mission_stats


def _admin() -> AccountAuthSubject:
    return AccountAuthSubject(
        id="admin-1",
        email="admin@example.com",
        name="Admin",
        role="admin",
        is_active=True,
        is_superuser=True,
    )


@pytest.mark.asyncio
async def test_admin_mission_stats_uses_mission_dashboard_service(monkeypatch) -> None:
    payload = {
        "kpis": {"total": 5, "success": 3, "failed": 1, "success_rate": 0.6},
        "time_series": [],
        "by_workspace_type": [{"type": "sci", "count": 5}],
    }
    service = SimpleNamespace(get_mission_stats=AsyncMock(return_value=payload))

    async def no_cache(*, cache_key, fetcher, cache_bust):
        assert cache_key == "analytics:mission-stats:30:day"
        assert cache_bust is True
        return await fetcher()

    monkeypatch.setattr("src.gateway.routers.admin_analytics.cached", no_cache)
    result = await mission_stats(
        range="30d",
        granularity="day",
        cache_bust=True,
        service=service,
        _admin=_admin(),
    )

    assert result == payload
    service.get_mission_stats.assert_awaited_once_with(range_days=30, granularity="day")
