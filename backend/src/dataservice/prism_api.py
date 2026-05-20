"""Public in-process Prism API for DataService."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.prism.adapters.latex import build_latex_adapter_metadata
from src.dataservice.domains.prism.contracts import (
    PrismFileCreateCommand,
    PrismFileProjection,
    PrismFileVersionCreateCommand,
    PrismFileVersionProjection,
    PrismPrimaryProjectCommand,
    PrismProjectProjection,
    PrismSurfaceProjection,
)
from src.dataservice.domains.prism.service import PrismDataDomainService


class PrismDataService:
    """Prism API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = PrismDataDomainService(session, autocommit=autocommit)

    async def ensure_primary_project(self, command: PrismPrimaryProjectCommand) -> PrismSurfaceProjection:
        return await self._domain.ensure_primary_project(command)

    async def ensure_latex_primary_project(
        self,
        *,
        workspace_id: str,
        title: str,
        latex_project_id: str,
        main_file: str = "main.tex",
        settings_json: dict[str, Any] | None = None,
        adapter_metadata_json: dict[str, Any] | None = None,
    ) -> PrismSurfaceProjection:
        metadata = dict(adapter_metadata_json or {})
        metadata.setdefault("latex_project_id", latex_project_id)
        return await self._domain.ensure_primary_project(
            PrismPrimaryProjectCommand(
                workspace_id=workspace_id,
                title=title,
                adapter_kind="latex",
                adapter_ref_id=latex_project_id,
                main_file=main_file,
                settings_json=dict(settings_json or {}),
                adapter_metadata_json=metadata,
            )
        )

    async def get_primary_project(self, workspace_id: str) -> PrismProjectProjection | None:
        return await self._domain.get_primary_project(workspace_id)

    async def get_surface(self, workspace_id: str) -> PrismSurfaceProjection | None:
        return await self._domain.get_surface(workspace_id)

    async def create_file(
        self,
        *,
        document_id: str,
        workspace_id: str,
        command: PrismFileCreateCommand,
    ) -> PrismFileProjection:
        return await self._domain.create_file(
            document_id=document_id,
            workspace_id=workspace_id,
            command=command,
        )

    async def append_file_version(
        self,
        command: PrismFileVersionCreateCommand,
    ) -> PrismFileVersionProjection | None:
        return await self._domain.append_file_version(command)


__all__ = ["PrismDataService", "build_latex_adapter_metadata"]
