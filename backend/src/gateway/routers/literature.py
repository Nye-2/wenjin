"""Literature router for literature management API endpoints.

This module provides REST endpoints for:
- Literature CRUD operations
- Literature batch import
- Literature count
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from src.academic.services.workspace_service import WorkspaceService
from src.database import User
from src.gateway.access_control import require_workspace_owner
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_literature_service, get_workspace_service
from src.services.literature_service import LiteratureService

router = APIRouter(prefix="/workspaces", tags=["literature"])


# ============ Request/Response Models ============

class CreateLiteratureRequest(BaseModel):
    """Request model for creating literature."""

    title: str
    authors: list[str] | None = None
    year: int | None = None
    citations: int | None = None
    venue: str | None = None
    quartile: str | None = None
    abstract: str | None = None
    doi: str | None = None
    source: str = "manual"
    is_core: bool = False


class UpdateLiteratureRequest(BaseModel):
    """Request model for updating literature."""

    title: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    citations: int | None = None
    venue: str | None = None
    quartile: str | None = None
    abstract: str | None = None
    doi: str | None = None
    source: str | None = None
    is_core: bool | None = None


class BatchImportRequest(BaseModel):
    """Request model for batch importing literature."""

    source: str
    artifact_ids: list[str] = Field(default_factory=list)


class LiteratureResponse(BaseModel):
    """Response model for literature entry."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    title: str
    authors: list[str]
    year: int | None = None
    citations: int | None = None
    venue: str | None = None
    quartile: str | None = None
    abstract: str | None = None
    doi: str | None = None
    source: str
    is_core: bool
    created_at: str | None = None
    updated_at: str | None = None


class LiteratureListResponse(BaseModel):
    """Response model for literature list."""

    items: list[LiteratureResponse]
    total: int
    core_count: int


class LiteratureCountResponse(BaseModel):
    """Response model for literature count."""

    total: int
    core: int


class BatchImportResponse(BaseModel):
    """Response model for batch import."""

    imported: int


# ============ Endpoints ============

@router.get(
    "/{workspace_id}/literature",
    response_model=LiteratureListResponse,
)
async def list_literature(
    workspace_id: str,
    source: str | None = None,
    is_core: bool | None = None,
    offset: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    literature_service: LiteratureService = Depends(get_literature_service),
):
    """List literature entries for a workspace.

    Args:
        workspace_id: UUID of the workspace
        source: Optional filter by source
        is_core: Optional filter by core reference status
        offset: Number of items to skip
        limit: Maximum number of items to return
        literature_service: Literature service instance

    Returns:
        List of literature entries with total and core counts
    """
    await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    result = await literature_service.list_literature(
        workspace_id=workspace_id,
        source=source,
        is_core=is_core,
        offset=offset,
        limit=limit,
    )
    return LiteratureListResponse(**result)


@router.post(
    "/{workspace_id}/literature",
    response_model=LiteratureResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_literature(
    workspace_id: str,
    request: CreateLiteratureRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    literature_service: LiteratureService = Depends(get_literature_service),
):
    """Create a new literature entry.

    Args:
        workspace_id: UUID of the workspace
        request: Literature creation request
        current_user: Current authenticated user
        literature_service: Literature service instance

    Returns:
        Created literature entry
    """
    await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    result = await literature_service.create_literature(
        workspace_id=workspace_id,
        title=request.title,
        authors=request.authors,
        year=request.year,
        citations=request.citations,
        venue=request.venue,
        quartile=request.quartile,
        abstract=request.abstract,
        doi=request.doi,
        source=request.source,
        is_core=request.is_core,
    )
    return LiteratureResponse(**result)


@router.post(
    "/{workspace_id}/literature/import",
    response_model=BatchImportResponse,
)
async def batch_import_literature(
    workspace_id: str,
    request: BatchImportRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    literature_service: LiteratureService = Depends(get_literature_service),
):
    """Batch import literature entries.

    Args:
        workspace_id: UUID of the workspace
        request: Batch import request with source and artifact IDs
        current_user: Current authenticated user
        literature_service: Literature service instance

    Returns:
        Number of imported entries
    """
    await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    result = await literature_service.batch_import(
        workspace_id=workspace_id,
        source=request.source,
        paper_ids=request.artifact_ids,
    )
    return BatchImportResponse(**result)


@router.patch(
    "/{workspace_id}/literature/{literature_id}",
    response_model=LiteratureResponse,
)
async def update_literature(
    workspace_id: str,
    literature_id: str,
    request: UpdateLiteratureRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    literature_service: LiteratureService = Depends(get_literature_service),
):
    """Update a literature entry.

    Args:
        workspace_id: UUID of the workspace
        literature_id: UUID of the literature entry
        request: Update request with fields to update
        current_user: Current authenticated user
        literature_service: Literature service instance

    Returns:
        Updated literature entry

    Raises:
        HTTPException: If literature not found
    """
    await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    update_data = request.model_dump(exclude_unset=True)
    result = await literature_service.update_literature(
        literature_id=literature_id,
        workspace_id=workspace_id,
        **update_data,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Literature not found",
        )

    return LiteratureResponse(**result)


@router.delete(
    "/{workspace_id}/literature/{literature_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_literature(
    workspace_id: str,
    literature_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    literature_service: LiteratureService = Depends(get_literature_service),
):
    """Delete a literature entry.

    Args:
        workspace_id: UUID of the workspace
        literature_id: UUID of the literature entry
        current_user: Current authenticated user
        literature_service: Literature service instance

    Raises:
        HTTPException: If literature not found
    """
    await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    success = await literature_service.delete_literature(
        literature_id,
        workspace_id=workspace_id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Literature not found",
        )


@router.get(
    "/{workspace_id}/literature/count",
    response_model=LiteratureCountResponse,
)
async def get_literature_count(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    literature_service: LiteratureService = Depends(get_literature_service),
):
    """Get literature count for a workspace.

    Args:
        workspace_id: UUID of the workspace
        literature_service: Literature service instance

    Returns:
        Total and core literature counts
    """
    await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    result = await literature_service.count_literature(workspace_id)
    return LiteratureCountResponse(**result)
