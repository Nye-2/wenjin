"""Academic-domain dependency factories."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.services import ArtifactService, ExtractionService, PaperService, WorkspaceService
from src.gateway.deps.core import get_db
from src.services.literature_service import LiteratureService


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


async def get_extraction_service(
    db: AsyncSession = Depends(get_db),
) -> ExtractionService:
    """Get extraction service instance."""
    return ExtractionService(db)


async def get_literature_service(
    db: AsyncSession = Depends(get_db),
) -> LiteratureService:
    """Get literature service instance."""
    return LiteratureService(db)
