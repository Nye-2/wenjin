"""Tests for admin dashboard aggregation."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.database import CreditTransactionType
from src.services.admin_dashboard_service import AdminDashboardService


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_get_dashboard_reports_real_credit_pool_and_overdraft_metrics() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarResult(6),
            _ScalarResult(5),
            _ScalarResult(1),
            _ScalarResult(4),
            _RowsResult([("thesis", 3), ("sci", 1)]),
            _ScalarResult(12),
            _ScalarResult(2),
            _ScalarResult(1),
            _ScalarResult(8),
            _ScalarResult(260),
            _ScalarResult(180),
            _ScalarResult(67),
            _ScalarResult(2),
            _ScalarResult(7),
            _ScalarResult(13),
            _ScalarResult(29),
            _RowsResult(
                [
                    (
                        "tx-chat-1",
                        "user-1",
                        CreditTransactionType.THREAD_TOKEN_CONSUME,
                        {"token_usage": {"total_tokens": 9000}},
                    ),
                    (
                        "tx-refund-1",
                        "user-1",
                        CreditTransactionType.REFUND,
                        {"original_transaction_id": "tx-chat-2"},
                    ),
                    (
                        "tx-chat-2",
                        "user-2",
                        CreditTransactionType.THREAD_TOKEN_CONSUME,
                        {"token_usage": {"total_tokens": 3000}},
                    ),
                ]
            ),
            _RowsResult(
                [
                    (
                        {
                            "token_usage": {
                                "input_tokens": 100,
                                "output_tokens": 40,
                                "total_tokens": 140,
                            }
                        },
                    ),
                    ({},),
                ]
            ),
            _RowsResult(
                [
                    (
                        {
                            "token_usage": {
                                "input_tokens": 70,
                                "output_tokens": 10,
                                "total_tokens": 80,
                            }
                        },
                    ),
                    ({},),
                ]
            ),
        ]
    )

    payload = await AdminDashboardService(db).get_dashboard()

    assert payload["summary"]["credits"] == {
        "total_issued": 260,
        "total_spent": 180,
        "in_circulation": 67,
        "manual_deductions": 13,
        "overdraft_users": 2,
        "overdraft_credits_total": 7,
        "total_transactions": 29,
    }
    assert payload["summary"]["workspaces"]["by_type"] == {"thesis": 3, "sci": 1}
    assert payload["summary"]["token_usage"]["thread"]["total_tokens"] == 9000
    assert payload["summary"]["token_usage"]["thread"]["transactions"] == 1
    assert payload["summary"]["token_usage"]["feature_tasks"]["total_tokens"] == 140
    assert payload["summary"]["token_usage"]["subagents"]["total_tokens"] == 80
    assert "recent_users" not in payload
    assert "top_spenders" not in payload
    assert "recent_admin_logs" not in payload
