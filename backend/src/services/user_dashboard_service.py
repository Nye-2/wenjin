"""User dashboard aggregation service."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import User, Workspace
from src.dataservice.execution_api import ExecutionDataService, ExecutionNodeProjection
from src.services.credit_service import CreditService
from src.services.thread_billing import combine_token_usage, normalize_token_usage


class UserDashboardService:
    """Aggregate user-facing dashboard data."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._execution = ExecutionDataService(db, autocommit=False)

    async def get_dashboard(self, user_id: str) -> dict[str, Any]:
        """Build user dashboard payload."""
        user = await self.db.get(User, user_id)
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
        token_usage = await self._get_token_usage_stats(
            user_id=user_id,
            thread_credit_status=thread_credit_status,
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
                "thread": thread_credit_status,
            },
            "workspaces": workspace_stats,
            "tasks": task_stats,
            "token_usage": token_usage,
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
        counts = await self._execution.count_executions_by_status(user_id=user_id)
        total = sum(counts.values())
        success = int(counts.get("success", 0)) + int(counts.get("completed", 0))
        # Only count terminal tasks (success + failed + cancelled) for completion rate
        terminal = success + int(counts.get("failed", 0)) + int(counts.get("cancelled", 0))
        completion_rate = float(round(success / terminal, 4)) if terminal else 0.0

        recent_executions = await self._execution.list_executions(
            user_id=user_id,
            limit=10,
        )
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
        remaining_free_tokens = max(policy.free_tokens - consumed_tokens, 0)
        can_start_thread = (
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
            "can_start_thread": can_start_thread,
            "overdraft_credits": max(-current_balance, 0),
        }

    async def _get_token_usage_stats(
        self,
        *,
        user_id: str,
        thread_credit_status: dict[str, Any],
    ) -> dict[str, Any]:
        """Build token usage aggregates for thread, feature tasks, and subagents."""
        executions = await self._execution.list_executions(
            user_id=user_id,
            limit=10000,
        )
        feature_usages = []
        for execution in executions:
            usage = None
            result = execution.result_json
            if isinstance(result, dict):
                usage = normalize_token_usage(result.get("token_usage"))
            if usage is not None:
                feature_usages.append(usage)
        feature_usage_total = combine_token_usage(feature_usages)

        nodes = await self._execution.list_nodes_by_execution_ids(
            [execution.id for execution in executions]
        )
        subagent_usages = []
        for node in nodes:
            usage = self._node_token_usage(node)
            if usage is not None:
                subagent_usages.append(usage)
        subagent_usage_total = combine_token_usage(subagent_usages)

        consumed_thread_tokens = max(
            int(thread_credit_status.get("consumed_tokens", 0) or 0),
            0,
        )
        free_thread_tokens = max(
            int(thread_credit_status.get("free_tokens", 0) or 0),
            0,
        )

        return {
            "thread": {
                "total_tokens": consumed_thread_tokens,
                "free_tokens": free_thread_tokens,
                "billable_tokens": max(consumed_thread_tokens - free_thread_tokens, 0),
                "remaining_free_tokens": max(
                    int(thread_credit_status.get("remaining_free_tokens", 0) or 0),
                    0,
                ),
            },
            "feature_tasks": {
                "input_tokens": (
                    feature_usage_total.input_tokens if feature_usage_total is not None else 0
                ),
                "output_tokens": (
                    feature_usage_total.output_tokens if feature_usage_total is not None else 0
                ),
                "total_tokens": (
                    feature_usage_total.total_tokens if feature_usage_total is not None else 0
                ),
                "records": len(executions),
                "records_with_usage": len(feature_usages),
            },
            "subagents": {
                "input_tokens": (
                    subagent_usage_total.input_tokens if subagent_usage_total is not None else 0
                ),
                "output_tokens": (
                    subagent_usage_total.output_tokens if subagent_usage_total is not None else 0
                ),
                "total_tokens": (
                    subagent_usage_total.total_tokens if subagent_usage_total is not None else 0
                ),
                "records": len(nodes),
                "records_with_usage": len(subagent_usages),
            },
        }

    @staticmethod
    def _node_token_usage(record: ExecutionNodeProjection) -> Any | None:
        usage = normalize_token_usage(record.token_usage)
        if usage is not None:
            return usage
        metadata = record.node_metadata if isinstance(record.node_metadata, dict) else {}
        usage = normalize_token_usage(metadata.get("token_usage"))
        if usage is not None:
            return usage
        output_data = record.output_data if isinstance(record.output_data, dict) else {}
        return normalize_token_usage(output_data.get("token_usage"))
