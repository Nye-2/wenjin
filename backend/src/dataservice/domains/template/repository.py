"""Workspace template repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.workspace_template import WorkspaceTemplate


class TemplateRepository:
    """DataService-owned persistence operations for workspace templates."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, template_id: str) -> WorkspaceTemplate | None:
        result = await self.session.execute(
            select(WorkspaceTemplate).where(WorkspaceTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    async def get_active(self, workspace_id: str) -> WorkspaceTemplate | None:
        result = await self.session.execute(
            select(WorkspaceTemplate)
            .where(
                WorkspaceTemplate.workspace_id == workspace_id,
                WorkspaceTemplate.is_active,
            )
            .order_by(WorkspaceTemplate.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_workspace(self, workspace_id: str) -> list[WorkspaceTemplate]:
        result = await self.session.execute(
            select(WorkspaceTemplate)
            .where(WorkspaceTemplate.workspace_id == workspace_id)
            .order_by(WorkspaceTemplate.updated_at.desc())
        )
        return list(result.scalars().all())

    async def deactivate_active_templates(
        self,
        *,
        workspace_id: str,
        exclude_template_id: str | None = None,
    ) -> None:
        stmt = update(WorkspaceTemplate).where(
            WorkspaceTemplate.workspace_id == workspace_id,
            WorkspaceTemplate.is_active,
        )
        if exclude_template_id is not None:
            stmt = stmt.where(WorkspaceTemplate.id != exclude_template_id)
        await self.session.execute(stmt.values(is_active=False))

    def create(self, values: dict[str, Any]) -> WorkspaceTemplate:
        template = WorkspaceTemplate(**values)
        self.session.add(template)
        return template
