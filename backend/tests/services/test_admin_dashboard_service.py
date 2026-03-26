"""Tests for admin dashboard credit transaction aggregation."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.services.admin_dashboard_service import AdminDashboardService


class _RowsResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


@pytest.mark.asyncio
async def test_recent_credit_transactions_include_metadata() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=_RowsResult(
            [
                (
                    type(
                        "Tx",
                        (),
                        {
                            "id": "tx-1",
                            "user_id": "user-1",
                            "transaction_type": type("TxType", (), {"value": "chat_token_consume"})(),
                            "amount": -2,
                            "balance_after": -1,
                            "description": "Chat token 扣费",
                            "feature_id": "chat",
                            "tx_metadata": {"overdraft_credits": 1},
                            "created_at": datetime(2026, 3, 26, tzinfo=UTC),
                        },
                    )(),
                    "user@example.com",
                    "User",
                )
            ]
        )
    )

    service = AdminDashboardService(db)
    items = await service._get_recent_credit_transactions()

    assert items[0]["metadata"]["overdraft_credits"] == 1
    assert items[0]["type"] == "chat_token_consume"
