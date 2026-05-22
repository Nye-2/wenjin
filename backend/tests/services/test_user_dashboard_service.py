"""Tests for user dashboard aggregation."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.dataservice_client.contracts.account import AccountUserPayload
from src.dataservice_client.contracts.execution import (
    ExecutionNodePayload,
    ExecutionPayload,
)
from src.dataservice_client.contracts.workspace import WorkspaceStatsPayload
from src.services.user_dashboard_service import UserDashboardService


class FakeDashboardDataServiceClient:
    def __init__(self) -> None:
        self.user = AccountUserPayload(
            id="user-1",
            email="user-1@example.com",
            name="User 1",
            role="user",
            is_active=True,
            is_superuser=False,
            credits=-2,
            total_credits_earned=100,
            total_credits_spent=102,
            created_at=datetime(2026, 3, 26, tzinfo=UTC),
            last_login=None,
        )
        self.workspace_stats = WorkspaceStatsPayload(
            total=0,
            by_type={},
            created_last_7d=0,
        )
        self.status_counts: dict[str, int] = {}
        self.executions: list[ExecutionPayload] = []
        self.nodes: list[ExecutionNodePayload] = []

    async def get_account_user(self, user_id: str) -> AccountUserPayload | None:
        return self.user if user_id == self.user.id else None

    async def get_workspace_stats_for_member(self, user_id: str) -> WorkspaceStatsPayload:
        return self.workspace_stats

    async def count_executions_by_status(self, *, user_id: str | None = None) -> dict[str, int]:
        return self.status_counts

    async def list_executions(
        self,
        *,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[ExecutionPayload]:
        return self.executions[:limit]

    async def list_execution_nodes_by_execution_ids(
        self,
        execution_ids: list[str],
    ) -> list[ExecutionNodePayload]:
        wanted = set(execution_ids)
        return [node for node in self.nodes if node.execution_id in wanted]


def _execution_projection(**overrides) -> ExecutionPayload:
    now = overrides.get("created_at") or datetime.now(UTC)
    return ExecutionPayload(
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


def _node_projection(**overrides) -> ExecutionNodePayload:
    now = overrides.get("created_at") or datetime.now(UTC)
    return ExecutionNodePayload(
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
    fake_client = FakeDashboardDataServiceClient()
    service = UserDashboardService(db, dataservice=fake_client)
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
    fake_client = FakeDashboardDataServiceClient()
    fake_client.executions = [
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
    fake_client.nodes = [
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
    service = UserDashboardService(db, dataservice=fake_client)
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
    fake_client = FakeDashboardDataServiceClient()
    fake_client.workspace_stats = WorkspaceStatsPayload(
        total=2,
        by_type={"thesis": 1, "sci": 1},
        created_last_7d=1,
    )
    service = UserDashboardService(db, dataservice=fake_client)

    stats = await service._get_workspace_stats("user-1")

    assert stats == {
        "total": 2,
        "by_type": {"thesis": 1, "sci": 1},
        "created_last_7d": 1,
    }
