"""LaTeX module router."""

from __future__ import annotations

from fastapi import APIRouter

from src.gateway.contracts.latex import (
    LatexCompileRequest,
    LatexFileChangeActionRequest,
    LatexFileChangeApplyRequest,
    LatexFileChangeRevertRequest,
    LatexUpdateProjectRequest,
)
from src.gateway.routers.latex_compile import router as compile_router
from src.gateway.routers.latex_feedback import router as feedback_router
from src.gateway.routers.latex_files import (
    apply_project_file_change,
    discard_project_file_change,
    preview_project_file_change,
    revert_project_file_change,
)
from src.gateway.routers.latex_files import (
    router as files_router,
)
from src.gateway.routers.latex_helpers import (
    _candidate_risk_level,
    _collect_archive_upload_payload,
    _compute_candidate_signature,
    _compute_revert_signature,
    _is_reserved_upload_path,
    _normalize_upload_relative_path,
    _profiled_comment,
    _read_upload_bytes_with_limit,
)
from src.gateway.routers.latex_projects import router as projects_router
from src.gateway.routers.latex_templates import router as templates_router
from src.gateway.routers.latex_upload import router as upload_router

router = APIRouter()

router.include_router(projects_router)
router.include_router(files_router)
router.include_router(feedback_router)
router.include_router(upload_router)
router.include_router(compile_router)
router.include_router(templates_router)


__all__ = [
    "router",
    "LatexCompileRequest",
    "LatexFileChangeActionRequest",
    "LatexFileChangeApplyRequest",
    "LatexFileChangeRevertRequest",
    "LatexUpdateProjectRequest",
    "_candidate_risk_level",
    "_collect_archive_upload_payload",
    "_compute_candidate_signature",
    "_compute_revert_signature",
    "_is_reserved_upload_path",
    "_normalize_upload_relative_path",
    "_profiled_comment",
    "_read_upload_bytes_with_limit",
    "apply_project_file_change",
    "discard_project_file_change",
    "preview_project_file_change",
    "revert_project_file_change",
]
