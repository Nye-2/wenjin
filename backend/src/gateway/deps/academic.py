from __future__ import annotations

"""Academic-domain dependency factories."""

from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.literature.index_service import IndexService
from src.academic.services import ArtifactService, PaperService, WorkspaceService
from src.gateway.deps.core import get_db
from src.services.literature_service import LiteratureService

if TYPE_CHECKING:
    from src.services.template_service import TemplateService


async def get_workspace_service(
    db: AsyncSession = Depends(get_db),
) -> WorkspaceService:
    """Get workspace service instance."""
    return WorkspaceService(db)


async def get_paper_service(
    db: AsyncSession = Depends(get_db),
) -> PaperService:
    """Get paper service instance."""
    return PaperService(db)


async def get_artifact_service(
    db: AsyncSession = Depends(get_db),
) -> ArtifactService:
    """Get artifact service instance."""
    return ArtifactService(db)


async def get_literature_service(
    db: AsyncSession = Depends(get_db),
) -> LiteratureService:
    """Get literature service instance."""
    return LiteratureService(db)


async def get_index_service(
    db: AsyncSession = Depends(get_db),
) -> IndexService:
    """Get literature index service instance."""
    return IndexService(db)


async def get_template_service(
    db: AsyncSession = Depends(get_db),
) -> TemplateService:
    from src.services.template_service import TemplateService
    return TemplateService(db)
