"""Tests for user dashboard aggregation."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.user_dashboard_service import UserDashboardService


@pytest.mark.asyncio
async def test_get_dashboard_includes_chat_credit_status() -> None:
    db = AsyncMock()
    db.get = AsyncMock(
        return_value=SimpleNamespace(
            id="user-1",
            email="user-1@example.com",
            name="User 1",
            is_superuser=False,
            is_active=True,
            created_at=datetime(2026, 3, 26, tzinfo=UTC),
            last_login=None,
            credits=-2,
            total_credits_earned=100,
            total_credits_spent=102,
        )
    )

    service = UserDashboardService(db)
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
        "src.services.user_dashboard_service.CreditService.get_chat_billing_policy",
        return_value=SimpleNamespace(enabled=True, free_tokens=100000, tokens_per_credit=10000),
    ), patch(
        "src.services.user_dashboard_service.CreditService.get_consumed_chat_tokens",
        AsyncMock(return_value=120000),
    ), patch(
        "src.services.user_dashboard_service.CreditService.can_start_chat_turn",
        AsyncMock(return_value=False),
    ) as can_start_chat_turn:
        payload = await service.get_dashboard("user-1")

    assert payload["credits"]["chat"] == {
        "enabled": True,
        "free_tokens": 100000,
        "tokens_per_credit": 10000,
        "consumed_tokens": 120000,
        "remaining_free_tokens": 0,
        "can_start_chat": False,
        "overdraft_credits": 2,
    }
    can_start_chat_turn.assert_not_called()
