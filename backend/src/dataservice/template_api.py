"""Public in-process workspace template API for DataService."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.template.service import DataServiceTemplateService


class TemplateDataService:
    """Workspace template API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = DataServiceTemplateService(session, autocommit=autocommit)

    async def get(self, template_id: str) -> Any | None:
        return await self._domain.get(template_id)

    async def get_active(self, workspace_id: str) -> Any | None:
        return await self._domain.get_active(workspace_id)

    async def list_by_workspace(self, workspace_id: str) -> list[Any]:
        return await self._domain.list_by_workspace(workspace_id)

    async def create(
        self,
        *,
        workspace_id: str,
        name: str,
        category: str,
        source_type: str,
        source_file_path: str | None = None,
        structure: dict[str, Any] | None = None,
        format_spec: dict[str, Any] | None = None,
        content_guidelines: dict[str, Any] | None = None,
        latex_preamble: str | None = None,
    ) -> Any:
        return await self._domain.create(
            workspace_id=workspace_id,
            name=name,
            category=category,
            source_type=source_type,
            source_file_path=source_file_path,
            structure=structure,
            format_spec=format_spec,
            content_guidelines=content_guidelines,
            latex_preamble=latex_preamble,
        )

    async def deactivate_active_templates(
        self,
        *,
        workspace_id: str,
        exclude_template_id: str | None = None,
    ) -> None:
        await self._domain.deactivate_active_templates(
            workspace_id=workspace_id,
            exclude_template_id=exclude_template_id,
        )
