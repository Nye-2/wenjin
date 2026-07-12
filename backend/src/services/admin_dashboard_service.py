"""Admin dashboard and management service."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.account import (
    AccountUserPayload,
    AccountUserRolePayload,
    AccountUserStatusPayload,
)
from src.dataservice_client.contracts.audit import AuditLogCreatePayload
from src.dataservice_client.provider import dataservice_client


class DashboardAdminAction(StrEnum):
    """Admin dashboard audit action contract."""

    CREDIT_GRANT = "credit_grant"
    CREDIT_DEDUCT = "credit_deduct"
    USER_ROLE_CHANGE = "user_role_change"
    USER_STATUS_CHANGE = "user_status_change"


class AdminDashboardService:
    """Service for admin dashboard metrics and lightweight user management."""

    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ):
        self._dataservice = dataservice

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

    async def get_dashboard(self) -> dict[str, Any]:
        """Aggregate admin dashboard payload."""
        now = datetime.now(UTC)
        async with self._client() as client:
            account_stats = await client.get_account_admin_stats()

        async with self._client() as client:
            workspace_stats = await client.get_admin_workspace_stats()

        task_total = 0
        task_running = 0
        task_failed_24h = 0

        async with self._client() as client:
            artifact_total = await client.count_workspace_artifacts()

        async with self._client() as client:
            credit_summary = (await client.get_credit_admin_summary()).model_dump(mode="json")
        token_usage_summary = await self._get_token_usage_summary()

        return {
            "summary": {
                "users": {
                    "total": account_stats.total_users,
                    "active": account_stats.active_users,
                    "admins": account_stats.admin_users,
                },
                "workspaces": {
                    "total": workspace_stats.total,
                    "by_type": workspace_stats.by_type,
                },
                "tasks": {
                    "total": task_total,
                    "running": task_running,
                    "failed_last_24h": task_failed_24h,
                },
                "artifacts": {
                    "total": artifact_total,
                },
                "credits": {
                    "total_issued": credit_summary["total_issued"],
                    "total_spent": credit_summary["total_spent"],
                    "in_circulation": credit_summary["in_circulation"],
                    "manual_deductions": credit_summary["manual_deductions"],
                    "overdraft_users": credit_summary["overdraft_users"],
                    "overdraft_credits_total": credit_summary["overdraft_credits_total"],
                    "total_transactions": credit_summary["total_transactions"],
                },
                "token_usage": token_usage_summary,
            },
            "updated_at": now.isoformat(),
        }

    async def get_mission_stats(
        self,
        *,
        range_days: int,
        granularity: str,
    ) -> dict[str, Any]:
        """Aggregate the admin task panel from MissionRun only."""

        created_since = datetime.now(UTC) - timedelta(days=range_days)
        async with self._client() as client:
            result = await client.missions.aggregate_stats(
                created_since=created_since,
                granularity=granularity,
            )
        return result.model_dump(mode="json")

    async def _get_token_usage_summary(self) -> dict[str, Any]:
        """Aggregate non-deduplicated token usage snapshots for admin overview."""
        async with self._client() as client:
            thread_summary = (await client.get_credit_thread_token_usage()).model_dump(mode="json")

        return {
            "thread": {
                "total_tokens": thread_summary["total_tokens"],
                "transactions": thread_summary["transactions"],
                "users": thread_summary["users"],
            },
            "subagents": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "records": 0,
                "records_with_usage": 0,
            },
        }

    async def list_users(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        is_active: bool | None = None,
        is_superuser: bool | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List users for admin table."""
        async with self._client() as client:
            result = await client.list_account_users(
                page=page,
                page_size=page_size,
                keyword=keyword,
                is_active=is_active,
                is_superuser=is_superuser,
            )
        users = result.users
        user_ids = [str(user.id) for user in users]
        workspace_counts: dict[str, int] = {}
        task_counts: dict[str, int] = {}
        if user_ids:
            async with self._client() as client:
                workspace_counts = await client.count_workspaces_by_member_ids(user_ids)

        return [
            self._user_to_dict(
                user,
                workspace_count=workspace_counts.get(str(user.id), 0),
                task_count=task_counts.get(str(user.id), 0),
            )
            for user in users
        ], result.total

    async def _count_active_admins(self) -> int:
        """Count currently active admin users."""
        async with self._client() as client:
            return await client.count_active_admins()

    async def update_user_status(self, *, user_id: str, is_active: bool) -> dict[str, Any]:
        """Enable or disable user account."""
        async with self._client() as client:
            user = await client.update_account_user_status(
                user_id,
                AccountUserStatusPayload(is_active=is_active),
            )
        if user is None:
            raise ValueError("User not found")
        return self._user_to_dict(user)

    async def update_user_role(self, *, user_id: str, role: str) -> dict[str, Any]:
        """Switch user role between user/admin."""
        role = role.lower().strip()
        if role not in {"user", "admin"}:
            raise ValueError("Unsupported role")

        async with self._client() as client:
            user = await client.update_account_user_role(
                user_id,
                AccountUserRolePayload(role=role),
            )
        if user is None:
            raise ValueError("User not found")
        return self._user_to_dict(user)

    async def create_admin_log(
        self,
        *,
        admin_id: str,
        action: DashboardAdminAction | str,
        target_user_id: str | None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> Any:
        """Persist admin audit log entry."""
        action_value = DashboardAdminAction(action).value
        async with self._client() as client:
            return await client.create_audit_log(
                AuditLogCreatePayload(
                    action=action_value,
                    user_id=admin_id,
                    target_type="user",
                    target_id=target_user_id,
                    payload=details or {},
                    ip=ip_address,
                )
            )

    async def list_admin_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        action: str | None = None,
        target_user_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List paginated admin logs with admin/target user metadata."""
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size

        action_enum = None
        if action:
            try:
                action_enum = DashboardAdminAction(action)
            except ValueError as exc:
                raise ValueError(f"Unsupported action: {action}") from exc

        async with self._client() as client:
            records, total = await client.list_catalog_admin_logs(
                action=action_enum.value if action_enum else None,
                target_user_id=target_user_id,
                offset=offset,
                limit=page_size,
            )

        return [
            {
                **record.model_dump(),
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }
            for record in records
        ], total

    def _user_to_dict(
        self,
        user: AccountUserPayload,
        *,
        workspace_count: int = 0,
        task_count: int = 0,
    ) -> dict[str, Any]:
        return {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "is_active": user.is_active,
            "credits": int(user.credits),
            "total_credits_earned": int(user.total_credits_earned),
            "total_credits_spent": int(user.total_credits_spent),
            "workspace_count": workspace_count,
            "task_count": task_count,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
        }
