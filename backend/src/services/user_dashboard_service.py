"""User dashboard aggregation service."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.provider import dataservice_client
from src.services.credit_service import CreditService


class UserDashboardService:
    """Aggregate user-facing dashboard data."""

    def __init__(
        self,
        db: AsyncSession | None = None,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ):
        self.db = db
        self._dataservice = dataservice

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

    async def get_dashboard(self, user_id: str) -> dict[str, Any]:
        """Build user dashboard payload."""
        async with self._client() as client:
            user = await client.get_account_user(user_id)
        if user is None:
            raise ValueError("User not found")

        credit_service = CreditService(self.db)
        workspace_stats = await self._get_workspace_stats(user_id)
        task_stats, recent_tasks = await self._get_task_stats(user_id)
        thread_credit_status = await self._get_thread_credit_status(
            user_id,
            credit_service=credit_service,
            current_balance=int(user.credits),
        )

        return {
            "profile": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login": user.last_login.isoformat() if user.last_login else None,
            },
            "credits": {
                "balance": int(user.credits),
                "total_earned": int(user.total_credits_earned),
                "total_spent": int(user.total_credits_spent),
                "costs": CreditService.get_public_workflow_costs(),
                "thread": thread_credit_status,
            },
            "workspaces": workspace_stats,
            "tasks": task_stats,
            "recent_tasks": recent_tasks,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    async def _get_workspace_stats(self, user_id: str) -> dict[str, Any]:
        async with self._client() as client:
            stats = await client.get_workspace_stats_for_member(user_id)
        return {
            "total": stats.total,
            "by_type": stats.by_type,
            "created_last_7d": stats.created_last_7d,
        }

    async def _get_task_stats(self, user_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        async with self._client() as client:
            counts = await client.count_executions_by_status(user_id=user_id)
        total = sum(counts.values())
        success = int(counts.get("success", 0)) + int(counts.get("completed", 0))
        # Only count terminal tasks (success + failed + cancelled) for completion rate
        terminal = success + int(counts.get("failed", 0)) + int(counts.get("cancelled", 0))
        completion_rate = float(round(success / terminal, 4)) if terminal else 0.0

        async with self._client() as client:
            recent_executions = await client.list_executions(user_id=user_id, limit=10)
        recent_tasks = [
            {
                "id": execution.id,
                "task_type": execution.execution_type,
                "status": execution.status,
                "progress": int(execution.progress),
                "message": execution.message,
                "created_at": execution.created_at.isoformat() if execution.created_at else None,
                "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            }
            for execution in recent_executions
        ]

        return (
            {
                "total": total,
                "success": success,
                "running": int(counts.get("running", 0)),
                "failed": int(counts.get("failed", 0)),
                "pending": int(counts.get("pending", 0)),
                "cancelled": int(counts.get("cancelled", 0)),
                "completion_rate": completion_rate,
            },
            recent_tasks,
        )

    async def _get_thread_credit_status(
        self,
        user_id: str,
        *,
        credit_service: CreditService,
        current_balance: int,
    ) -> dict[str, Any]:
        """Build thread-specific credit status for dashboard display."""
        policy = credit_service.get_thread_billing_policy()
        consumed_tokens = await credit_service.get_consumed_thread_tokens(user_id)
        can_start_thread = (
            (not policy.enabled)
            or consumed_tokens < policy.free_tokens
            or current_balance > 0
        )

        return {
            "enabled": policy.enabled,
            "can_start_thread": can_start_thread,
            "overdraft_credits": max(-current_balance, 0),
            "billing_unit": "credits",
            "pricing": "usage_based",
        }
