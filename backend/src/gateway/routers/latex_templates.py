"""LaTeX template endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.contracts.latex import LatexTemplateListResponse
from src.gateway.deps.core import get_db
from src.services.latex import LatexTemplateService

router = APIRouter(prefix="/latex", tags=["latex"])


@router.get("/templates", response_model=LatexTemplateListResponse)
async def list_templates(
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatexTemplateListResponse:
    service = LatexTemplateService(db)
    templates = await service.list_templates()
    return LatexTemplateListResponse(templates=templates)  # type: ignore[arg-type]
