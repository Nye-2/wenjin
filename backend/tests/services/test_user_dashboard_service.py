"""Tests for user dashboard aggregation."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.dataservice.domains.execution.contracts import (
    ExecutionNodeProjection,
    ExecutionRecordProjection,
)
from src.dataservice.domains.workspace.contracts import WorkspaceStatsRecord
from src.services.user_dashboard_service import UserDashboardService


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def _execution_projection(**overrides) -> ExecutionRecordProjection:
    now = overrides.get("created_at") or datetime.now(UTC)
    return ExecutionRecordProjection(
        id=overrides.get("id", "exec-1"),
        user_id=overrides.get("user_id", "user-1"),
        workspace_id=overrides.get("workspace_id", "ws-1"),
        thread_id=overrides.get("thread_id"),
        execution_type=overrides.get("execution_type", "feature"),
        capability_id=overrides.get("capability_id"),
        status=overrides.get("status", "completed"),
        task_brief_json=overrides.get("task_brief_json", {}),
        result_json=overrides.get("result_json"),
        node_states_json={},
        progress=overrides.get("progress", 100),
        artifact_ids=[],
        next_actions=[],
        child_execution_ids=[],
        created_at=now,
        updated_at=now,
    )


def _node_projection(**overrides) -> ExecutionNodeProjection:
    now = overrides.get("created_at") or datetime.now(UTC)
    return ExecutionNodeProjection(
        id=overrides.get("id", "node-1"),
        execution_id=overrides.get("execution_id", "exec-1"),
        node_id=overrides.get("node_id", "phase__task"),
        node_type=overrides.get("node_type", "react"),
        status=overrides.get("status", "completed"),
        token_usage=overrides.get("token_usage"),
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_get_dashboard_includes_thread_credit_status() -> None:
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
    service._get_token_usage_stats = AsyncMock(
        return_value={
            "thread": {
                "total_tokens": 120000,
                "free_tokens": 100000,
                "billable_tokens": 20000,
                "remaining_free_tokens": 0,
            },
            "feature_tasks": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "records": 0,
                "records_with_usage": 0,
            },
            "subagents": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "records": 0,
                "records_with_usage": 0,
            },
        }
    )

    with patch(
        "src.services.user_dashboard_service.CreditService.get_thread_billing_policy",
        return_value=SimpleNamespace(enabled=True, free_tokens=100000, tokens_per_credit=10000),
    ), patch(
        "src.services.user_dashboard_service.CreditService.get_consumed_thread_tokens",
        AsyncMock(return_value=120000),
    ), patch(
        "src.services.user_dashboard_service.CreditService.can_start_thread_turn",
        AsyncMock(return_value=False),
    ) as can_start_thread_turn:
        payload = await service.get_dashboard("user-1")

    assert payload["credits"]["thread"] == {
        "enabled": True,
        "free_tokens": 100000,
        "tokens_per_credit": 10000,
        "consumed_tokens": 120000,
        "remaining_free_tokens": 0,
        "can_start_thread": False,
        "overdraft_credits": 2,
    }
    assert payload["token_usage"]["thread"]["total_tokens"] == 120000
    can_start_thread_turn.assert_not_called()


@pytest.mark.asyncio
async def test_get_token_usage_stats_aggregates_feature_and_subagent_usage() -> None:
    db = AsyncMock()
    service = UserDashboardService(db)
    service._execution.list_executions = AsyncMock(
        return_value=[
            _execution_projection(
                id="exec-1",
                result_json={
                    "token_usage": {
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "total_tokens": 120,
                    }
                },
            ),
            _execution_projection(id="exec-2", result_json={}),
        ]
    )
    service._execution.list_nodes_by_execution_ids = AsyncMock(
        return_value=[
            _node_projection(
                id="node-1",
                execution_id="exec-1",
                token_usage={
                    "input_tokens": 30,
                    "output_tokens": 10,
                    "total_tokens": 40,
                },
            ),
            _node_projection(id="node-2", execution_id="exec-2"),
        ]
    )
    stats = await service._get_token_usage_stats(
        user_id="user-1",
        thread_credit_status={
            "consumed_tokens": 5000,
            "free_tokens": 3000,
            "remaining_free_tokens": 0,
        },
    )

    assert stats["thread"]["total_tokens"] == 5000
    assert stats["thread"]["billable_tokens"] == 2000
    assert stats["feature_tasks"]["total_tokens"] == 120
    assert stats["feature_tasks"]["records"] == 2
    assert stats["feature_tasks"]["records_with_usage"] == 1
    assert stats["subagents"]["total_tokens"] == 40
    assert stats["subagents"]["records"] == 2
    assert stats["subagents"]["records_with_usage"] == 1


@pytest.mark.asyncio
async def test_get_workspace_stats_uses_dataservice_projection() -> None:
    db = AsyncMock()
    service = UserDashboardService(db)
    service._workspace.get_workspace_stats_for_member = AsyncMock(
        return_value=WorkspaceStatsRecord(
            total=2,
            by_type={"thesis": 1, "sci": 1},
            created_last_7d=1,
        )
    )

    stats = await service._get_workspace_stats("user-1")

    assert stats == {
        "total": 2,
        "by_type": {"thesis": 1, "sci": 1},
        "created_last_7d": 1,
    }
