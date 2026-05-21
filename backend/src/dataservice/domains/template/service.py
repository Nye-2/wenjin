"""Workspace template command/query service."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.template.repository import TemplateRepository


class DataServiceTemplateService:
    """DataService-owned workspace template lifecycle operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = TemplateRepository(session)

    async def get(self, template_id: str) -> Any | None:
        return await self.repository.get(template_id)

    async def get_active(self, workspace_id: str) -> Any | None:
        return await self.repository.get_active(workspace_id)

    async def list_by_workspace(self, workspace_id: str) -> list[Any]:
        return await self.repository.list_by_workspace(workspace_id)

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
        await self.repository.deactivate_active_templates(workspace_id=workspace_id)
        template = self.repository.create(
            {
                "workspace_id": workspace_id,
                "name": name,
                "category": category,
                "source_type": source_type,
                "source_file_path": source_file_path,
                "structure": structure,
                "format_spec": format_spec,
                "content_guidelines": content_guidelines,
                "latex_preamble": latex_preamble,
                "is_active": True,
                "is_builtin": False,
            }
        )
        await self._finish(template)
        return template

    async def deactivate_active_templates(
        self,
        *,
        workspace_id: str,
        exclude_template_id: str | None = None,
    ) -> None:
        await self.repository.deactivate_active_templates(
            workspace_id=workspace_id,
            exclude_template_id=exclude_template_id,
        )
        await self._finish()

    async def _finish(self, record: Any | None = None) -> None:
        if self.autocommit:
            await self.session.commit()
            if record is not None:
                await self.session.refresh(record)
            return
        await self.session.flush()
