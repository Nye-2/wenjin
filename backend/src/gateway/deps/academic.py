from __future__ import annotations

"""Academic-domain dependency factories."""

from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.services.artifact_service import ArtifactService
from src.academic.services.workspace_service import WorkspaceService
from src.dataservice.source_api import SourceDataService
from src.gateway.deps.core import get_db

if TYPE_CHECKING:
    from src.services.template_service import TemplateService


async def get_workspace_service(
    db: AsyncSession = Depends(get_db),
) -> WorkspaceService:
    """Get workspace service instance."""
    return WorkspaceService(db)


async def get_artifact_service(
    db: AsyncSession = Depends(get_db),
) -> ArtifactService:
    """Get artifact service instance."""
    return ArtifactService(db)


async def get_reference_service(
    db: AsyncSession = Depends(get_db),
) -> SourceDataService:
    """Get Source DataService instance for citation context."""
    return SourceDataService(db, autocommit=False)


async def get_reference_index_service(
    db: AsyncSession = Depends(get_db),
) -> SourceDataService:
    """Get Source DataService projection adapter for literature indexing."""
    return SourceDataService(db, autocommit=False)


async def get_template_service(
    db: AsyncSession = Depends(get_db),
) -> TemplateService:
    from src.services.template_service import TemplateService
    return TemplateService(db)
