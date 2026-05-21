"""Admin dashboard and management service."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AdminActionType, User
from src.dataservice.asset_api import AssetDataService
from src.dataservice.catalog_api import CatalogDataService
from src.dataservice.credit_api import CreditDataService
from src.dataservice.execution_api import ExecutionDataService, ExecutionNodeProjection
from src.dataservice.workspace_api import WorkspaceDataService
from src.services.thread_billing import combine_token_usage, normalize_token_usage


class AdminDashboardService:
    """Service for admin dashboard metrics and lightweight user management."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._assets = AssetDataService(db, autocommit=False)
        self._catalog = CatalogDataService(db, autocommit=False)
        self._credit = CreditDataService(db, autocommit=False)
        self._execution = ExecutionDataService(db, autocommit=False)
        self._workspace = WorkspaceDataService(db, autocommit=False)

    async def get_dashboard(self) -> dict[str, Any]:
        """Aggregate admin dashboard payload."""
        now = datetime.now(UTC)
        since_24h = now - timedelta(hours=24)

        total_users = int((await self.db.execute(select(func.count()).select_from(User))).scalar() or 0)
        active_users = int(
            (
                await self.db.execute(
                    select(func.count()).where(User.is_active == True)  # noqa: E712
                )
            ).scalar()
            or 0
        )
        admin_users = int(
            (
                await self.db.execute(
                    select(func.count()).where(User.is_superuser == True)  # noqa: E712
                )
            ).scalar()
            or 0
        )

        workspace_stats = await self._workspace.get_admin_workspace_stats()

        task_total = await self._execution.count_executions()
        task_running = await self._execution.count_executions(
            status=["running"],
        )
        task_failed_24h = await self._execution.count_executions(
            status=["failed"],
            created_since=since_24h,
        )

        artifact_total = await self._assets.count_legacy_artifacts()

        credit_summary = await self._credit.get_admin_credit_summary()
        token_usage_summary = await self._get_token_usage_summary()

        return {
            "summary": {
                "users": {
                    "total": total_users,
                    "active": active_users,
                    "admins": admin_users,
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

    async def _get_token_usage_summary(self) -> dict[str, Any]:
        """Aggregate non-deduplicated token usage snapshots for admin overview."""
        thread_summary = await self._credit.get_thread_token_usage_summary()

        executions = await self._execution.list_executions(limit=100000)
        feature_usages = []
        for execution in executions:
            result = execution.result_json
            usage = normalize_token_usage(
                result.get("token_usage") if isinstance(result, dict) else None
            )
            if usage is not None:
                feature_usages.append(usage)
        feature_total = combine_token_usage(feature_usages)

        subagent_nodes = await self._execution.list_nodes_by_execution_ids(
            [execution.id for execution in executions]
        )
        subagent_usages = []
        for node in subagent_nodes:
            usage = self._node_token_usage(node)
            if usage is not None:
                subagent_usages.append(usage)
        subagent_total = combine_token_usage(subagent_usages)

        return {
            "thread": {
                "total_tokens": thread_summary["total_tokens"],
                "transactions": thread_summary["transactions"],
                "users": thread_summary["users"],
            },
            "feature_tasks": {
                "input_tokens": feature_total.input_tokens if feature_total is not None else 0,
                "output_tokens": feature_total.output_tokens if feature_total is not None else 0,
                "total_tokens": feature_total.total_tokens if feature_total is not None else 0,
                "records": len(executions),
                "records_with_usage": len(feature_usages),
            },
            "subagents": {
                "input_tokens": subagent_total.input_tokens if subagent_total is not None else 0,
                "output_tokens": subagent_total.output_tokens if subagent_total is not None else 0,
                "total_tokens": subagent_total.total_tokens if subagent_total is not None else 0,
                "records": len(subagent_nodes),
                "records_with_usage": len(subagent_usages),
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
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size

        base_query = select(User)
        if keyword:
            pattern = f"%{keyword}%"
            base_query = base_query.where(
                or_(
                    User.email.ilike(pattern),
                    User.name.ilike(pattern),
                )
            )
        if is_active is not None:
            base_query = base_query.where(User.is_active == is_active)
        if is_superuser is not None:
            base_query = base_query.where(User.is_superuser == is_superuser)

        total = int(
            (
                await self.db.execute(
                    select(func.count()).select_from(base_query.subquery())
                )
            ).scalar()
            or 0
        )

        rows = await self.db.execute(
            base_query.order_by(desc(User.created_at)).offset(offset).limit(page_size)
        )
        users = rows.scalars().all()
        user_ids = [str(user.id) for user in users]
        workspace_counts: dict[str, int] = {}
        task_counts: dict[str, int] = {}
        if user_ids:
            workspace_counts = await self._workspace.count_workspaces_by_member_ids(user_ids)

            task_counts = await self._execution.count_executions_by_user_ids(user_ids)

        return [
            self._user_to_dict(
                user,
                workspace_count=workspace_counts.get(str(user.id), 0),
                task_count=task_counts.get(str(user.id), 0),
            )
            for user in users
        ], total

    async def _count_active_admins(self) -> int:
        """Count currently active admin users."""
        return int(
            (
                await self.db.execute(
                    select(func.count())
                    .where(User.is_superuser == True)  # noqa: E712
                    .where(User.is_active == True)  # noqa: E712
                )
            ).scalar()
            or 0
        )

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

    async def update_user_status(self, *, user_id: str, is_active: bool) -> dict[str, Any]:
        """Enable or disable user account."""
        user = await self.db.get(User, user_id)
        if user is None:
            raise ValueError("User not found")
        if not is_active and user.is_superuser and user.is_active:
            active_admins = await self._count_active_admins()
            if active_admins <= 1:
                raise ValueError("Cannot disable the last active admin")
        user.is_active = is_active
        await self.db.commit()
        await self.db.refresh(user)
        return self._user_to_dict(user)

    async def update_user_role(self, *, user_id: str, role: str) -> dict[str, Any]:
        """Switch user role between user/admin."""
        role = role.lower().strip()
        if role not in {"user", "admin"}:
            raise ValueError("Unsupported role")

        user = await self.db.get(User, user_id)
        if user is None:
            raise ValueError("User not found")
        if role == "user" and user.is_superuser and user.is_active:
            active_admins = await self._count_active_admins()
            if active_admins <= 1:
                raise ValueError("Cannot demote the last active admin")

        user.is_superuser = role == "admin"
        await self.db.commit()
        await self.db.refresh(user)
        return self._user_to_dict(user)

    async def create_admin_log(
        self,
        *,
        admin_id: str,
        action: AdminActionType,
        target_user_id: str | None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> Any:
        """Persist admin audit log entry."""
        return await CatalogDataService(self.db).record_admin_log(
            admin_id=admin_id,
            action=action.value,
            target_user_id=target_user_id,
            target_type="user",
            details=details or {},
            ip_address=ip_address,
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
                action_enum = AdminActionType(action)
            except ValueError as exc:
                raise ValueError(f"Unsupported action: {action}") from exc

        records, total = await self._catalog.list_admin_logs(
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
        user: User,
        *,
        workspace_count: int = 0,
        task_count: int = 0,
    ) -> dict[str, Any]:
        return {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": "admin" if user.is_superuser else "user",
            "is_active": user.is_active,
            "credits": int(user.credits),
            "total_credits_earned": int(user.total_credits_earned),
            "total_credits_spent": int(user.total_credits_spent),
            "workspace_count": workspace_count,
            "task_count": task_count,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
        }
