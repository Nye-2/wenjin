"""HTTP API endpoints for thesis generation.

This module provides REST API endpoints for managing thesis generation tasks.
Uses thread-safe task storage that can be replaced with Redis/database in production.
"""

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field, field_validator

from .task_storage import create_thesis_task, get_storage

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


@router.post("/generate", response_model=ThesisStatusResponse)
async def generate_thesis(
    request: ThesisGenerateRequest,
    background_tasks: BackgroundTasks,
) -> ThesisStatusResponse:
    """Start thesis generation task.

    This endpoint:
    1. Creates a new thesis generation task
    2. Returns task_id for status polling
    3. Actual generation runs in background

    Args:
        request: Thesis generation request parameters
        background_tasks: FastAPI background tasks

    Returns:
        Initial task status
    """
    # Create task using thread-safe storage
    task = create_thesis_task(
        workspace_id=request.workspace_id,
        paper_title=request.paper_title,
        message="Task created, waiting to start",
    )

    # TODO: Implement background task execution when workflow is ready
    # from .workflow.runner import run_thesis_workflow
    # background_tasks.add_task(
    #     run_thesis_workflow,
    #     task.task_id,
    #     request.model_dump(),
    # )

    logger.info(f"[Thesis] Created task {task.task_id} for workspace {request.workspace_id}")

    return ThesisStatusResponse(
        task_id=task.task_id,
        status=task.status,
        progress=task.progress,
        current_phase=task.current_phase,
        message=task.message,
    )


@router.get("/status/{task_id}", response_model=ThesisStatusResponse)
async def get_status(task_id: str) -> ThesisStatusResponse:
    """Get thesis generation task status.

    Args:
        task_id: Task ID from generate endpoint

    Returns:
        Current task status and progress

    Raises:
        HTTPException: 404 if task not found
    """
    task = get_storage().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    return ThesisStatusResponse(
        task_id=task.task_id,
        status=task.status,
        progress=task.progress,
        current_phase=task.current_phase,
        message=task.message,
        pdf_path=task.pdf_path,
        error=task.error,
    )


@router.delete("/cancel/{task_id}")
async def cancel_task(task_id: str) -> dict[str, str]:
    """Cancel a running thesis generation task.

    Args:
        task_id: Task ID to cancel

    Returns:
        Cancellation status

    Raises:
        HTTPException: 404 if task not found, 400 if task cannot be cancelled
    """
    storage = get_storage()
    task = storage.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    if task.status in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=400, detail=f"Cannot cancel task with status: {task.status}"
        )

    # Atomic update using storage
    updated = storage.update_task(task_id, {
        "status": "cancelled",
        "message": "Task cancelled by user",
    })

    if not updated:
        raise HTTPException(status_code=500, detail="Failed to cancel task")

    logger.info(f"[Thesis] Cancelled task {task_id}")

    return {
        "task_id": task_id,
        "status": "cancelled",
        "message": "Task cancelled",
    }


@router.get("/preview/{task_id}", response_model=ThesisPreviewResponse)
async def get_preview(task_id: str) -> ThesisPreviewResponse:
    """Get thesis preview content.

    Returns the current LaTeX content for preview.

    Args:
        task_id: Task ID

    Returns:
        Preview content with LaTeX and section progress

    Raises:
        HTTPException: 404 if task not found
    """
    task = get_storage().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    return ThesisPreviewResponse(
        task_id=task.task_id,
        latex_content=task.latex_content,
        sections_completed=task.sections_completed,
        sections_total=task.sections_total,
    )


@router.get("/list")
async def list_tasks(workspace_id: str | None = None) -> list[dict[str, Any]]:
    """List all thesis generation tasks.

    Args:
        workspace_id: Optional workspace ID filter

    Returns:
        List of tasks
    """
    tasks = get_storage().list_tasks(workspace_id=workspace_id)
    return [t.to_dict() for t in tasks]
