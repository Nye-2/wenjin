"""Thread-scoped upload router for thread attachments."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile

from src.application.services.upload_application_service import (
    ThreadUploadResponse,
    UploadApplicationService,
)
from src.dataservice_client import AsyncDataServiceClient
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.gateway.deps import (
    get_artifact_service,
    get_dataservice_client,
    get_task_service,
    get_thread_service,
    get_upload_preprocessor,
    get_workspace_service,
)
from src.gateway.routers.thread_contracts import ThreadUploadKind
from src.services import ThreadService
from src.services.upload_preprocessor import UploadPreprocessor

router = APIRouter(prefix="/threads/{thread_id}/uploads", tags=["uploads"])


@router.post("", response_model=ThreadUploadResponse)
async def upload_thread_files(
    thread_id: str,
    files: list[UploadFile] = File(...),
    kind: ThreadUploadKind = Form(...),
    workspace_id: str | None = Form(default=None),
    current_user: AccountAuthSubject = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
    workspace_service: Any = Depends(get_workspace_service),
    artifact_service: Any = Depends(get_artifact_service),
    task_service: Any = Depends(get_task_service),
    upload_preprocessor: UploadPreprocessor = Depends(get_upload_preprocessor),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> ThreadUploadResponse:
    """Upload one or more files into a thread-scoped sandbox uploads directory."""
    service = UploadApplicationService(
        thread_service=thread_service,
        workspace_service=workspace_service,
        artifact_service=artifact_service,
        task_service=task_service,
        upload_preprocessor=upload_preprocessor,
        dataservice=dataservice,
    )
    return await service.upload_thread_files(
        thread_id=thread_id,
        files=files,
        kind=kind,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
    )
