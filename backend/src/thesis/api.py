"""HTTP API endpoints for thesis generation.

This module provides a backward-compatible thesis API surface backed by the
unified async task infrastructure.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field, field_validator

from src.application.errors import ApplicationError
from src.application.handlers.feature_execution_handler import get_feature_execution_handler
from src.application.handlers.thesis_api_handler import ThesisApiHandler
from src.application.results import ThesisCancelResult, ThesisPreviewResult, ThesisStatusResult
from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.dependencies import get_task_service
from src.gateway.error_mapping import to_http_exception
from src.task.service import TaskService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["thesis"])


class ThesisGenerateRequest(BaseModel):
    """Request to generate thesis."""

    workspace_id: str = Field(min_length=1, description="Workspace ID")
    paper_title: str = Field(min_length=1, description="Thesis title")
    discipline: str = Field(default="计算机科学", description="Academic discipline")
    abstract_content: str = Field(description="Thesis abstract")
    framework_json: dict[str, Any] = Field(description="Framework from framework-designer skill")
    enable_search: bool = Field(default=True, description="Enable literature search")
    enable_images: bool = Field(default=True, description="Enable figure generation")

    @field_validator("paper_title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate paper title is not empty."""
        if not v or not v.strip():
            raise ValueError("Paper title cannot be empty")
        return v.strip()

    @field_validator("framework_json")
    @classmethod
    def validate_framework(cls, v: dict) -> dict:
        """Validate framework has required structure."""
        if not isinstance(v, dict):
            raise ValueError("Framework must be a JSON object")
        # Basic validation - framework should have some content
        return v


class ThesisStatusResponse(BaseModel):
    """Response for thesis generation status."""

    task_id: str
    status: str  # pending, running, completed, failed, cancelled
    progress: float
    current_phase: str | None = None
    message: str | None = None
    pdf_path: str | None = None
    error: str | None = None


class ThesisPreviewResponse(BaseModel):
    """Response for thesis preview."""

    task_id: str
    latex_content: str
    sections_completed: int
    sections_total: int
async def get_thesis_api_handler(
    task_service: TaskService = Depends(get_task_service),
    feature_execution_handler=Depends(get_feature_execution_handler),
) -> ThesisApiHandler:
    """Get thesis API compatibility handler."""
    return ThesisApiHandler(
        task_service=task_service,
        feature_execution_handler=feature_execution_handler,
    )


@router.post("/generate", response_model=ThesisStatusResponse)
async def generate_thesis(
    request: ThesisGenerateRequest,
    current_user: User = Depends(get_current_user),
    handler: ThesisApiHandler = Depends(get_thesis_api_handler),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> ThesisStatusResponse:
    """Start thesis generation task.

    This endpoint:
    1. Creates a new thesis generation task
    2. Returns task_id for status polling
    3. Actual generation runs in background

    Args:
        request: Thesis generation request parameters
        current_user: Current authenticated user
        task_service: Unified task service

    Returns:
        Initial task status
    """
    from src.academic.cache.redis_client import redis_client
    from src.config import redis_settings

    runtime_redis = (
        redis_client
        if redis_settings.enabled and redis_client._client is not None
        else None
    )

    try:
        result = await handler.generate(
            request,
            idempotency_key=idempotency_key,
            redis_client=runtime_redis,
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    payload = result.to_dict() if isinstance(result, ThesisStatusResult) else result
    return ThesisStatusResponse(**payload)


@router.get("/status/{task_id}", response_model=ThesisStatusResponse)
async def get_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
    handler: ThesisApiHandler = Depends(get_thesis_api_handler),
) -> ThesisStatusResponse:
    """Get thesis generation task status.

    Args:
        task_id: Task ID from generate endpoint

    Returns:
        Current task status and progress

    Raises:
        HTTPException: 404 if task not found
    """
    try:
        result = await handler.get_status(task_id, str(current_user.id))
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    payload = result.to_dict() if isinstance(result, ThesisStatusResult) else result
    return ThesisStatusResponse(**payload)


@router.delete("/cancel/{task_id}")
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    handler: ThesisApiHandler = Depends(get_thesis_api_handler),
) -> dict[str, str]:
    """Cancel a running thesis generation task.

    Args:
        task_id: Task ID to cancel

    Returns:
        Cancellation status

    Raises:
        HTTPException: 404 if task not found, 400 if task cannot be cancelled
    """
    try:
        result = await handler.cancel(task_id, str(current_user.id))
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    return result.to_dict() if isinstance(result, ThesisCancelResult) else result


@router.get("/preview/{task_id}", response_model=ThesisPreviewResponse)
async def get_preview(
    task_id: str,
    current_user: User = Depends(get_current_user),
    handler: ThesisApiHandler = Depends(get_thesis_api_handler),
) -> ThesisPreviewResponse:
    """Get thesis preview content.

    Returns the current LaTeX content for preview.

    Args:
        task_id: Task ID

    Returns:
        Preview content with LaTeX and section progress

    Raises:
        HTTPException: 404 if task not found
    """
    try:
        result = await handler.get_preview(task_id, str(current_user.id))
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    payload = result.to_dict() if isinstance(result, ThesisPreviewResult) else result
    return ThesisPreviewResponse(**payload)


@router.get("/list")
async def list_tasks(
    workspace_id: str | None = None,
    current_user: User = Depends(get_current_user),
    handler: ThesisApiHandler = Depends(get_thesis_api_handler),
) -> list[dict[str, Any]]:
    """List all thesis generation tasks.

    Args:
        workspace_id: Optional workspace ID filter

    Returns:
        List of tasks
    """
    try:
        results = await handler.list_tasks(
            user_id=str(current_user.id),
            workspace_id=workspace_id,
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    return [result.to_dict() if isinstance(result, ThesisStatusResult) else result for result in results]
