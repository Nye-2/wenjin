"""Admin dashboard Mission cutover contracts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.services.admin_dashboard_service import AdminDashboardService


class _DashboardDataService:
    async def get_credit_thread_token_usage(self):
        return SimpleNamespace(
            model_dump=lambda **_: {
                "total_tokens": 321,
                "transactions": 4,
                "users": 2,
            }
        )


@pytest.mark.asyncio
async def test_token_usage_summary_has_no_removed_feature_bucket() -> None:
    service = AdminDashboardService(dataservice=_DashboardDataService())  # type: ignore[arg-type]

    summary = await service._get_token_usage_summary()

    assert summary["thread"] == {
        "total_tokens": 321,
        "transactions": 4,
        "users": 2,
    }
    assert "feature" + "_tasks" not in summary
    assert summary["subagents"]["total_tokens"] == 0
