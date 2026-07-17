"""LaTeX module router."""

from __future__ import annotations

from fastapi import APIRouter

from src.gateway.contracts.latex import LatexUpdateProjectRequest
from src.gateway.routers.latex_files import (
    router as files_router,
)
from src.gateway.routers.latex_helpers import (
    _collect_archive_upload_payload,
    _is_reserved_upload_path,
    _normalize_upload_relative_path,
    _read_upload_bytes_with_limit,
)
from src.gateway.routers.latex_projects import router as projects_router
from src.gateway.routers.latex_templates import router as templates_router
from src.gateway.routers.latex_upload import router as upload_router

router = APIRouter()

router.include_router(projects_router)
router.include_router(files_router)
router.include_router(upload_router)
router.include_router(templates_router)


__all__ = [
    "router",
    "LatexUpdateProjectRequest",
    "_collect_archive_upload_payload",
    "_is_reserved_upload_path",
    "_normalize_upload_relative_path",
    "_read_upload_bytes_with_limit",
]
