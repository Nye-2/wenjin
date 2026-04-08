"""User dashboard aggregation service."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import TaskRecord, User, Workspace
from src.services.credit_service import CreditService


class UserDashboardService:
    """Aggregate user-facing dashboard data."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard(self, user_id: str) -> dict[str, Any]:
        """Build user dashboard payload."""
        user = await self.db.get(User, user_id)
        if user is None:
            raise ValueError("User not found")

        credit_service = CreditService(self.db)
        workspace_stats = await self._get_workspace_stats(user_id)
        task_stats, recent_tasks = await self._get_task_stats(user_id)
        chat_credit_status = await self._get_chat_credit_status(
            user_id,
            credit_service=credit_service,
            current_balance=int(user.credits),
        )

        return {
            "profile": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "role": "admin" if user.is_superuser else "user",
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login": user.last_login.isoformat() if user.last_login else None,
            },
            "credits": {
                "balance": int(user.credits),
                "total_earned": int(user.total_credits_earned),
                "total_spent": int(user.total_credits_spent),
                "costs": CreditService.get_workflow_costs(),
                "chat": chat_credit_status,
            },
            "workspaces": workspace_stats,
            "tasks": task_stats,
            "recent_tasks": recent_tasks,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    async def _get_workspace_stats(self, user_id: str) -> dict[str, Any]:
        by_type_rows = await self.db.execute(
            select(Workspace.type, func.count())
            .where(Workspace.user_id == user_id)
            .group_by(Workspace.type)
        )
        by_type = {
            (workspace_type.value if hasattr(workspace_type, "value") else str(workspace_type)): int(count)
            for workspace_type, count in by_type_rows.all()
        }
        total = sum(by_type.values())

        created_recent = await self.db.execute(
            select(func.count())
            .where(Workspace.user_id == user_id)
            .where(Workspace.created_at >= datetime.now(UTC) - timedelta(days=7))
        )
        created_last_7d = int(created_recent.scalar() or 0)

        return {
            "total": total,
            "by_type": by_type,
            "created_last_7d": created_last_7d,
        }

    async def _get_task_stats(self, user_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        stats_rows = await self.db.execute(
            select(TaskRecord.status, func.count())
            .where(TaskRecord.user_id == user_id)
            .group_by(TaskRecord.status)
        )
        counts = {status: int(count) for status, count in stats_rows.all()}
        total = sum(counts.values())
        success = int(counts.get("success", 0))
        # Only count terminal tasks (success + failed + cancelled) for completion rate
        terminal = success + int(counts.get("failed", 0)) + int(counts.get("cancelled", 0))
        completion_rate = float(round(success / terminal, 4)) if terminal else 0.0

        recent_result = await self.db.execute(
            select(TaskRecord)
            .where(TaskRecord.user_id == user_id)
            .order_by(TaskRecord.created_at.desc())
            .limit(10)
        )
        recent_tasks = [
            {
                "id": task.id,
                "task_type": task.task_type,
                "status": task.status,
                "progress": int(task.progress),
                "message": task.message,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }
            for task in recent_result.scalars().all()
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

    async def _get_chat_credit_status(
        self,
        user_id: str,
        *,
        credit_service: CreditService,
        current_balance: int,
    ) -> dict[str, Any]:
        """Build chat-specific credit status for dashboard display."""
        policy = credit_service.get_chat_billing_policy()
        consumed_tokens = await credit_service.get_consumed_chat_tokens(user_id)
        remaining_free_tokens = max(policy.free_tokens - consumed_tokens, 0)
        can_start_chat = (
            (not policy.enabled)
            or consumed_tokens < policy.free_tokens
            or current_balance > 0
        )

        return {
            "enabled": policy.enabled,
            "free_tokens": policy.free_tokens,
            "tokens_per_credit": policy.tokens_per_credit,
            "consumed_tokens": consumed_tokens,
            "remaining_free_tokens": remaining_free_tokens,
            "can_start_chat": can_start_chat,
            "overdraft_credits": max(-current_balance, 0),
        }
