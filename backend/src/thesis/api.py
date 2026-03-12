"""HTTP API endpoints for thesis generation.

This module provides a backward-compatible thesis API surface backed by the
unified async task infrastructure.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.academic.cache.redis_client import redis_client
from src.database import User, get_db_session
from src.gateway.routers.auth import get_current_user
from src.gateway.routers.tasks import get_task_service
from src.task.service import TaskService
from src.task.store import TaskStore

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


def _map_task_status(status: str) -> str:
    """Map generic task statuses to thesis API statuses."""
    if status == "success":
        return "completed"
    return status


def _merge_task_details(task_status: dict[str, Any]) -> dict[str, Any]:
    """Merge runtime metadata with final task result."""
    details: dict[str, Any] = {}
    metadata = task_status.get("metadata")
    result = task_status.get("result")
    if isinstance(metadata, dict):
        details.update(metadata)
    if isinstance(result, dict):
        details.update(result)
    return details


def _to_thesis_status_response(task_status: dict[str, Any]) -> ThesisStatusResponse:
    """Convert a generic task status payload to thesis API response."""
    details = _merge_task_details(task_status)
    progress = float(task_status.get("progress", 0)) / 100
    return ThesisStatusResponse(
        task_id=task_status["task_id"],
        status=_map_task_status(task_status["status"]),
        progress=max(0.0, min(progress, 1.0)),
        current_phase=details.get("current_phase"),
        message=task_status.get("message"),
        pdf_path=details.get("pdf_path"),
        error=task_status.get("error"),
    )


@router.post("/generate", response_model=ThesisStatusResponse)
async def generate_thesis(
    request: ThesisGenerateRequest,
    current_user: User = Depends(get_current_user),
    task_service: TaskService = Depends(get_task_service),
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
    task_id = await task_service.submit_task(
        user_id=str(current_user.id),
        task_type="thesis_generation",
        payload=request.model_dump(),
    )
    logger.info("[Thesis] Submitted unified task %s for workspace %s", task_id, request.workspace_id)

    return ThesisStatusResponse(
        task_id=task_id,
        status="pending",
        progress=0.0,
        current_phase="init",
        message="Task submitted",
    )


@router.get("/status/{task_id}", response_model=ThesisStatusResponse)
async def get_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
    task_service: TaskService = Depends(get_task_service),
) -> ThesisStatusResponse:
    """Get thesis generation task status.

    Args:
        task_id: Task ID from generate endpoint

    Returns:
        Current task status and progress

    Raises:
        HTTPException: 404 if task not found
    """
    task_status = await task_service.get_task_status(task_id, str(current_user.id))
    if not task_status:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    return _to_thesis_status_response(task_status)


@router.delete("/cancel/{task_id}")
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    task_service: TaskService = Depends(get_task_service),
) -> dict[str, str]:
    """Cancel a running thesis generation task.

    Args:
        task_id: Task ID to cancel

    Returns:
        Cancellation status

    Raises:
        HTTPException: 404 if task not found, 400 if task cannot be cancelled
    """
    success = await task_service.cancel_task(task_id, str(current_user.id))
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or cannot be cancelled")

    logger.info(f"[Thesis] Cancelled task {task_id}")

    return {
        "task_id": task_id,
        "status": "cancelled",
        "message": "Task cancelled",
    }


@router.get("/preview/{task_id}", response_model=ThesisPreviewResponse)
async def get_preview(
    task_id: str,
    current_user: User = Depends(get_current_user),
    task_service: TaskService = Depends(get_task_service),
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
    task_status = await task_service.get_task_status(task_id, str(current_user.id))
    if not task_status:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    details = _merge_task_details(task_status)

    return ThesisPreviewResponse(
        task_id=task_id,
        latex_content=details.get("latex_content", ""),
        sections_completed=details.get("sections_completed", 0),
        sections_total=details.get("sections_total", 0),
    )


@router.get("/list")
async def list_tasks(
    workspace_id: str | None = None,
    current_user: User = Depends(get_current_user),
    task_service: TaskService = Depends(get_task_service),
) -> list[dict[str, Any]]:
    """List all thesis generation tasks.

    Args:
        workspace_id: Optional workspace ID filter

    Returns:
        List of tasks
    """
    async with get_db_session() as db:
        store = TaskStore(redis_client, db)
        records = await store.list_user_tasks(
            user_id=str(current_user.id),
            task_type="thesis_generation",
            limit=100,
        )

    filtered_records = [
        record for record in records
        if workspace_id is None or (record.payload or {}).get("workspace_id") == workspace_id
    ]

    results: list[dict[str, Any]] = []
    for record in filtered_records:
        status = await task_service.get_task_status(record.id, str(current_user.id))
        if status:
            thesis_status = _to_thesis_status_response(status)
            results.append(thesis_status.model_dump())
    return results
