"""LaTeX template endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.contracts.latex import LatexTemplateListResponse
from src.dataservice_client import AsyncDataServiceClient
from src.gateway.deps.core import get_dataservice_client
from src.services.latex import LatexTemplateService

router = APIRouter(prefix="/prism/latex-adapter", tags=["latex"])


@router.get("/templates", response_model=LatexTemplateListResponse)
async def list_templates(
    _current_user: User = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> LatexTemplateListResponse:
    service = LatexTemplateService(dataservice=dataservice)
    templates = await service.list_templates()
    return LatexTemplateListResponse(templates=templates)  # type: ignore[arg-type]
