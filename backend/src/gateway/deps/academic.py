from __future__ import annotations

"""Academic-domain dependency factories."""

from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.services.artifact_service import ArtifactService
from src.academic.services.workspace_service import WorkspaceService
from src.dataservice_client import AsyncDataServiceClient
from src.gateway.deps.core import get_dataservice_client, get_db

if TYPE_CHECKING:
    from src.services.template_service import TemplateService


class SourceIndexService:
    """Small runtime adapter for literature context lookups."""

    def __init__(self, dataservice: AsyncDataServiceClient) -> None:
        self._dataservice = dataservice

    async def get_workspace_toc_summary(self, workspace_id: str) -> str:
        return await self._dataservice.get_source_toc_summary(workspace_id=workspace_id)


async def get_workspace_service(
    db: AsyncSession = Depends(get_db),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> WorkspaceService:
    """Get workspace service instance."""
    return WorkspaceService(db, dataservice=dataservice)


async def get_artifact_service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> ArtifactService:
    """Get artifact service instance."""
    return ArtifactService(dataservice=dataservice)


async def get_reference_service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> AsyncDataServiceClient:
    """Get DataService client for citation context."""
    return dataservice


async def get_reference_index_service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> SourceIndexService:
    """Get DataService-backed literature index adapter."""
    return SourceIndexService(dataservice)


async def get_template_service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> TemplateService:
    from src.services.template_service import TemplateService
    return TemplateService(dataservice=dataservice)
