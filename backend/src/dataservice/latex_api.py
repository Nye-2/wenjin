"""Public in-process LaTeX adapter API for DataService."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.latex.service import DataServiceLatexService


class LatexDataService:
    """LaTeX adapter persistence API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = DataServiceLatexService(session, autocommit=autocommit)

    async def list_projects_by_user(
        self,
        user_id: str,
        *,
        include_trashed: bool = False,
    ) -> list[Any]:
        return await self._domain.list_projects_by_user(
            user_id,
            include_trashed=include_trashed,
        )

    async def get_project(self, project_id: str) -> Any | None:
        return await self._domain.get_project(project_id)

    async def get_owned_project(self, *, project_id: str, user_id: str) -> Any | None:
        return await self._domain.get_owned_project(project_id=project_id, user_id=user_id)

    async def get_workspace_primary_project(
        self,
        *,
        workspace_id: str,
        owner_user_id: str,
        template: str | None = None,
    ) -> Any | None:
        return await self._domain.get_workspace_primary_project(
            workspace_id=workspace_id,
            owner_user_id=owner_user_id,
            template=template,
        )

    async def create_project(
        self,
        *,
        user_id: str,
        name: str,
        template_id: str | None = None,
    ) -> Any:
        return await self._domain.create_project(
            user_id=user_id,
            name=name,
            template_id=template_id,
        )

    async def update_project(self, project: Any, **kwargs: Any) -> Any:
        return await self._domain.update_project(project, **kwargs)

    async def touch_project(self, project: Any, **kwargs: Any) -> Any:
        return await self._domain.touch_project(project, **kwargs)

    async def attach_workspace_project(self, project: Any, *, workspace_id: str) -> Any:
        return await self._domain.attach_workspace_project(
            project,
            workspace_id=workspace_id,
        )

    async def soft_delete_project(self, project: Any) -> Any:
        return await self._domain.soft_delete_project(project)

    async def delete_project(self, project: Any) -> None:
        await self._domain.delete_project(project)

    async def get_template(self, template_id: str) -> Any | None:
        return await self._domain.get_template(template_id)

    async def ensure_default_templates(self) -> None:
        await self._domain.ensure_default_templates()

    async def list_templates(self) -> list[Any]:
        return await self._domain.list_templates()
