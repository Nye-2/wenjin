"""LaTeX adapter repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.latex_compile_history import LatexCompileHistory
from src.database.models.latex_project import LatexProject
from src.database.models.latex_template import LatexTemplate


class LatexRepository:
    """DataService-owned persistence operations for LaTeX adapter tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_projects_by_user(
        self,
        user_id: str,
        *,
        include_trashed: bool = False,
    ) -> list[LatexProject]:
        stmt = select(LatexProject).where(LatexProject.user_id == user_id)
        if not include_trashed:
            stmt = stmt.where(LatexProject.trashed.is_(False))
        stmt = stmt.order_by(LatexProject.updated_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_project(self, project_id: str) -> LatexProject | None:
        getter = getattr(self.session, "get", None)
        if callable(getter):
            return await getter(LatexProject, project_id)
        result = await self.session.execute(
            select(LatexProject).where(LatexProject.id == project_id).limit(1)
        )
        return _scalar_one_or_none(result)

    async def get_owned_project(
        self,
        *,
        project_id: str,
        user_id: str,
    ) -> LatexProject | None:
        stmt = select(LatexProject).where(
            LatexProject.id == project_id,
            LatexProject.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_workspace_primary_project(
        self,
        *,
        workspace_id: str,
        owner_user_id: str,
        template: str | None = None,
    ) -> LatexProject | None:
        params: dict[str, Any] = {
            "workspace_id": workspace_id,
            "owner_user_id": owner_user_id,
        }
        result = await self.session.execute(
            text(
                """
                select id
                from latex_projects
                where user_id = :owner_user_id
                  and workspace_id = :workspace_id
                  and surface_role = 'primary_manuscript'
                order by updated_at desc
                limit 1
                """
            ),
            params,
        )
        row = result.mappings().first()
        if row is None:
            return None
        return await self.get_project(str(row["id"]))

    def create_project(self, values: dict[str, Any]) -> LatexProject:
        project = LatexProject(**values)
        self.session.add(project)
        return project

    async def delete_project(self, project: LatexProject) -> None:
        await self.session.delete(project)

    async def get_template(self, template_id: str) -> LatexTemplate | None:
        return await self.session.get(LatexTemplate, template_id)

    async def has_templates(self) -> bool:
        found = (await self.session.execute(select(LatexTemplate.id).limit(1))).scalar_one_or_none()
        return found is not None

    def create_template(self, values: dict[str, Any]) -> LatexTemplate:
        template = LatexTemplate(**values)
        self.session.add(template)
        return template

    async def upsert_template(self, values: dict[str, Any]) -> LatexTemplate:
        template_id = str(values["id"])
        template = await self.get_template(template_id)
        if template is None:
            return self.create_template(values)
        for key, value in values.items():
            if key == "id":
                continue
            setattr(template, key, value)
        return template

    async def list_templates(self) -> list[LatexTemplate]:
        result = await self.session.execute(
            select(LatexTemplate).order_by(
                LatexTemplate.featured.desc(),
                LatexTemplate.id.asc(),
            )
        )
        return list(result.scalars().all())

    def create_compile_history(self, values: dict[str, Any]) -> LatexCompileHistory:
        history = LatexCompileHistory(**values)
        self.session.add(history)
        return history

    async def get_compile_history(self, history_id: str) -> LatexCompileHistory | None:
        return await self.session.get(LatexCompileHistory, history_id)

    async def list_compile_history(self, project_id: str) -> list[LatexCompileHistory]:
        stmt = (
            select(LatexCompileHistory)
            .where(LatexCompileHistory.project_id == project_id)
            .order_by(LatexCompileHistory.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_compile_history(self, history: LatexCompileHistory) -> None:
        await self.session.delete(history)


def _scalar_one_or_none(result: Any) -> Any | None:
    scalar_one_or_none = getattr(result, "scalar_one_or_none", None)
    if callable(scalar_one_or_none):
        return scalar_one_or_none()
    scalars = getattr(result, "scalars", None)
    if callable(scalars):
        values = list(scalars().all())
        return values[0] if values else None
    return None
