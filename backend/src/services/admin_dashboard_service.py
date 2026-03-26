"""Admin dashboard and management service."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.database import (
    AdminActionType,
    AdminLog,
    Artifact,
    CreditTransaction,
    CreditTransactionType,
    TaskRecord,
    User,
    Workspace,
)


class AdminDashboardService:
    """Service for admin dashboard metrics and lightweight user management."""

    def __init__(self, db: AsyncSession):
        self.db = db

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

        workspace_total = int(
            (await self.db.execute(select(func.count()).select_from(Workspace))).scalar()
            or 0
        )
        workspace_rows = await self.db.execute(
            select(Workspace.type, func.count()).group_by(Workspace.type)
        )
        workspace_by_type = {
            (workspace_type.value if hasattr(workspace_type, "value") else str(workspace_type)): int(count)
            for workspace_type, count in workspace_rows.all()
        }

        task_total = int((await self.db.execute(select(func.count()).select_from(TaskRecord))).scalar() or 0)
        task_running = int(
            (
                await self.db.execute(
                    select(func.count()).where(TaskRecord.status == "running")
                )
            ).scalar()
            or 0
        )
        task_failed_24h = int(
            (
                await self.db.execute(
                    select(func.count())
                    .where(TaskRecord.status == "failed")
                    .where(TaskRecord.created_at >= since_24h)
                )
            ).scalar()
            or 0
        )

        artifact_total = int((await self.db.execute(select(func.count()).select_from(Artifact))).scalar() or 0)

        credits_issued = int(
            (
                await self.db.execute(
                    select(func.coalesce(func.sum(User.total_credits_earned), 0))
                )
            ).scalar()
            or 0
        )
        credits_spent = int(
            (
                await self.db.execute(
                    select(func.coalesce(func.sum(User.total_credits_spent), 0))
                )
            ).scalar()
            or 0
        )
        credit_balance_total = int(
            (
                await self.db.execute(
                    select(func.coalesce(func.sum(User.credits), 0))
                )
            ).scalar()
            or 0
        )
        overdraft_users = int(
            (
                await self.db.execute(
                    select(func.count()).where(User.credits < 0)
                )
            ).scalar()
            or 0
        )
        overdraft_credits_total = int(
            (
                await self.db.execute(
                    select(func.coalesce(func.sum(func.abs(User.credits)), 0)).where(
                        User.credits < 0
                    )
                )
            ).scalar()
            or 0
        )
        manual_deductions_total = int(
            (
                await self.db.execute(
                    select(func.coalesce(func.sum(func.abs(CreditTransaction.amount)), 0)).where(
                        CreditTransaction.transaction_type == CreditTransactionType.ADMIN_DEDUCT
                    )
                )
            ).scalar()
            or 0
        )
        tx_total = int(
            (await self.db.execute(select(func.count()).select_from(CreditTransaction))).scalar()
            or 0
        )

        return {
            "summary": {
                "users": {
                    "total": total_users,
                    "active": active_users,
                    "admins": admin_users,
                },
                "workspaces": {
                    "total": workspace_total,
                    "by_type": workspace_by_type,
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
                    "total_issued": credits_issued,
                    "total_spent": credits_spent,
                    "in_circulation": credit_balance_total,
                    "manual_deductions": manual_deductions_total,
                    "overdraft_users": overdraft_users,
                    "overdraft_credits_total": overdraft_credits_total,
                    "total_transactions": tx_total,
                },
            },
            "updated_at": now.isoformat(),
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
            workspace_rows = await self.db.execute(
                select(Workspace.user_id, func.count())
                .where(Workspace.user_id.in_(user_ids))
                .group_by(Workspace.user_id)
            )
            workspace_counts = {
                str(user_id): int(count)
                for user_id, count in workspace_rows.all()
            }

            task_rows = await self.db.execute(
                select(TaskRecord.user_id, func.count())
                .where(TaskRecord.user_id.in_(user_ids))
                .group_by(TaskRecord.user_id)
            )
            task_counts = {
                str(user_id): int(count)
                for user_id, count in task_rows.all()
            }

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
    ) -> AdminLog:
        """Persist admin audit log entry."""
        log = AdminLog(
            admin_id=admin_id,
            action=action,
            target_type="user",
            target_user_id=target_user_id,
            details=details or {},
            ip_address=ip_address,
        )
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

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

        admin_alias = aliased(User)
        target_alias = aliased(User)

        conditions = []
        if action_enum:
            conditions.append(AdminLog.action == action_enum)
        if target_user_id:
            conditions.append(AdminLog.target_user_id == target_user_id)

        filtered_logs = select(AdminLog)
        if conditions:
            filtered_logs = filtered_logs.where(*conditions)

        total = int(
            (
                await self.db.execute(
                    select(func.count()).select_from(filtered_logs.subquery())
                )
            ).scalar()
            or 0
        )

        rows = await self.db.execute(
            select(
                AdminLog,
                admin_alias.email,
                admin_alias.name,
                target_alias.email,
                target_alias.name,
            )
            .join(admin_alias, AdminLog.admin_id == admin_alias.id)
            .outerjoin(target_alias, AdminLog.target_user_id == target_alias.id)
            .where(*conditions)
            .order_by(desc(AdminLog.created_at))
            .offset(offset)
            .limit(page_size)
        )

        items: list[dict[str, Any]] = []
        for log, admin_email, admin_name, target_email, target_name in rows.all():
            items.append(
                {
                    "id": str(log.id),
                    "action": log.action.value,
                    "target_type": log.target_type,
                    "target_user_id": log.target_user_id,
                    "details": log.details or {},
                    "ip_address": log.ip_address,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                    "admin": {
                        "id": str(log.admin_id),
                        "email": admin_email,
                        "name": admin_name,
                    },
                    "target_user": (
                        {
                            "id": str(log.target_user_id),
                            "email": target_email,
                            "name": target_name,
                        }
                        if log.target_user_id
                        else None
                    ),
                }
            )

        return items, total

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
