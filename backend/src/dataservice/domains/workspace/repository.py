"""Workspace aggregate repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models.thread import Thread
from src.database.models.workspace import Workspace, WorkspaceType
from src.database.models.workspace_settings import WorkspaceSettings
from src.dataservice.domains.workspace.contracts import (
    WorkspaceMembershipRole,
    WorkspaceMembershipStatus,
)
from src.dataservice.domains.workspace.models import WorkspaceMembership


class WorkspaceRepository:
    """Persistence operations for the workspace aggregate."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def create_workspace(
        self,
        *,
        created_by_user_id: str,
        name: str,
        workspace_type: WorkspaceType,
        description: str | None,
        settings_json: dict[str, Any],
    ) -> Workspace:
        workspace = Workspace(
            user_id=created_by_user_id,
            name=name,
            type=workspace_type,
            description=description,
            config=settings_json,
        )
        self.session.add(workspace)
        return workspace

    async def get_workspace(self, workspace_id: str) -> Workspace | None:
        result = await self.session.execute(
            select(Workspace)
            .options(selectinload(Workspace.settings))
            .where(Workspace.id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def get_workspace_bridge_row(self, workspace_id: str) -> dict[str, Any] | None:
        result = await self.session.execute(
            text(
                """
                select id, user_id, name, type
                from workspaces
                where id = :workspace_id
                limit 1
                """
            ),
            {"workspace_id": workspace_id},
        )
        row = result.mappings().first()
        return dict(row) if row is not None else None

    async def lock_workspace_for_update(self, workspace_id: str) -> None:
        await self.session.execute(
            select(Workspace.id)
            .where(Workspace.id == workspace_id)
            .with_for_update()
        )

    async def list_workspaces_for_member(self, user_id: str) -> list[Workspace]:
        statement = (
            select(Workspace)
            .options(selectinload(Workspace.settings))
            .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
            .where(
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.status == WorkspaceMembershipStatus.ACTIVE.value,
            )
            .order_by(Workspace.updated_at.desc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_workspaces_by_type(self) -> list[tuple[Any, int]]:
        result = await self.session.execute(
            select(Workspace.type, func.count()).group_by(Workspace.type)
        )
        return [(workspace_type, int(count)) for workspace_type, count in result.all()]

    async def count_active_members_with_workspaces(self) -> int:
        result = await self.session.execute(
            select(func.count(distinct(WorkspaceMembership.user_id))).where(
                WorkspaceMembership.status == WorkspaceMembershipStatus.ACTIVE.value
            )
        )
        return int(result.scalar() or 0)

    async def count_workspaces_by_member_ids(self, user_ids: list[str]) -> dict[str, int]:
        if not user_ids:
            return {}
        result = await self.session.execute(
            select(WorkspaceMembership.user_id, func.count(distinct(WorkspaceMembership.workspace_id)))
            .where(
                WorkspaceMembership.user_id.in_(user_ids),
                WorkspaceMembership.status == WorkspaceMembershipStatus.ACTIVE.value,
            )
            .group_by(WorkspaceMembership.user_id)
        )
        return {str(user_id): int(count) for user_id, count in result.all()}

    async def has_active_membership(
        self,
        *,
        workspace_id: str,
        user_id: str,
    ) -> bool:
        statement = select(WorkspaceMembership.id).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.status == WorkspaceMembershipStatus.ACTIVE.value,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None

    def create_owner_membership(
        self,
        *,
        workspace_id: str,
        user_id: str,
    ) -> WorkspaceMembership:
        membership = WorkspaceMembership(
            workspace_id=workspace_id,
            user_id=user_id,
            role=WorkspaceMembershipRole.OWNER.value,
            status=WorkspaceMembershipStatus.ACTIVE.value,
        )
        self.session.add(membership)
        return membership

    async def ensure_owner_membership(
        self,
        *,
        workspace_id: str,
        user_id: str,
    ) -> WorkspaceMembership:
        statement = select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
        result = await self.session.execute(statement)
        membership = result.scalar_one_or_none()
        if membership is None:
            return self.create_owner_membership(workspace_id=workspace_id, user_id=user_id)
        membership.role = WorkspaceMembershipRole.OWNER.value
        membership.status = WorkspaceMembershipStatus.ACTIVE.value
        return membership

    async def count_active_owners(self, workspace_id: str) -> int:
        statement = select(WorkspaceMembership.id).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.role == WorkspaceMembershipRole.OWNER.value,
            WorkspaceMembership.status == WorkspaceMembershipStatus.ACTIVE.value,
        )
        result = await self.session.execute(statement)
        return len(list(result.scalars().all()))

    async def get_workspace_settings(self, workspace_id: str) -> WorkspaceSettings | None:
        result = await self.session.execute(select(WorkspaceSettings).where(WorkspaceSettings.workspace_id == workspace_id))
        return result.scalar_one_or_none()

    async def ensure_workspace_settings(
        self,
        *,
        workspace_id: str,
        settings_json: dict[str, Any],
    ) -> WorkspaceSettings:
        settings = await self.get_workspace_settings(workspace_id)
        if settings is None:
            settings = WorkspaceSettings(workspace_id=workspace_id, settings_json=settings_json)
            self.session.add(settings)
            return settings
        settings.settings_json = settings_json
        return settings

    def create_workspace_settings(
        self,
        *,
        workspace_id: str,
        settings_json: dict[str, Any],
    ) -> WorkspaceSettings:
        settings = WorkspaceSettings(workspace_id=workspace_id, settings_json=settings_json)
        self.session.add(settings)
        return settings

    def create_workspace_settings_from_values(
        self,
        *,
        workspace_id: str,
        values: dict[str, Any],
    ) -> WorkspaceSettings:
        settings = WorkspaceSettings(workspace_id=workspace_id, **values)
        self.session.add(settings)
        return settings

    async def delete_workspace_settings(self, workspace_id: str) -> int:
        result = await self.session.execute(delete(WorkspaceSettings).where(WorkspaceSettings.workspace_id == workspace_id))
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def get_thread(self, thread_id: str) -> Thread | None:
        result = await self.session.execute(select(Thread).where(Thread.id == thread_id))
        return result.scalar_one_or_none()

    async def delete_workspace(self, workspace_id: str) -> int:
        result = await self.session.execute(delete(Workspace).where(Workspace.id == workspace_id))
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
