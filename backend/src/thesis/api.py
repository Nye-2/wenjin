"""HTTP API endpoints for thesis generation."""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["thesis"])


# In-memory task storage (would be replaced with proper task queue in production)
_thesis_tasks: dict[str, dict[str, Any]] = {}


class ThesisGenerateRequest(BaseModel):
    """Request to generate thesis."""

    workspace_id: str = Field(description="Workspace ID")
    paper_title: str = Field(description="Thesis title")
    discipline: str = Field(default="计算机科学", description="Academic discipline")
    abstract_content: str = Field(description="Thesis abstract")
    framework_json: dict = Field(description="Framework from framework-designer skill")
    enable_search: bool = Field(default=True, description="Enable literature search")
    enable_images: bool = Field(default=True, description="Enable figure generation")


class ThesisStatusResponse(BaseModel):
    """Response for thesis generation status."""

    task_id: str
    status: str  # pending, running, completed, failed
    progress: float
    current_phase: str | None = None
    message: str | None = None
    pdf_path: str | None = None
    error: str | None = None


def get_thesis_task_status(task_id: str) -> dict[str, Any] | None:
    """Get thesis task status from storage."""
    return _thesis_tasks.get(task_id)


@router.post("/generate", response_model=dict)
async def generate_thesis(
    request: ThesisGenerateRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Start thesis generation task.

    This endpoint:
    1. Creates a new thesis generation task
    2. Returns task_id for status polling
    3. Actual generation runs in background
    """
    task_id = str(uuid.uuid4())[:12]

    # Initialize task status
    _thesis_tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0.0,
        "current_phase": "init",
        "message": "Task created, waiting to start",
    }

    # TODO: Add background task execution
    # background_tasks.add_task(run_thesis_workflow, task_id, request)

    logger.info(f"[Thesis] Created task {task_id} for workspace {request.workspace_id}")

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Thesis generation task created",
    }


@router.get("/status/{task_id}", response_model=ThesisStatusResponse)
async def get_status(task_id: str) -> ThesisStatusResponse:
    """Get thesis generation task status.

    Args:
        task_id: Task ID from generate endpoint

    Returns:
        Current task status and progress
    """
    task = get_thesis_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return ThesisStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        progress=task["progress"],
        current_phase=task.get("current_phase"),
        message=task.get("message"),
        pdf_path=task.get("pdf_path"),
        error=task.get("error"),
    )


@router.delete("/cancel/{task_id}")
async def cancel_task(task_id: str) -> dict:
    """Cancel a running thesis generation task.

    Args:
        task_id: Task ID to cancel

    Returns:
        Cancellation status
    """
    task = get_thesis_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["status"] in ("completed", "failed"):
        raise HTTPException(
            status_code=400, detail=f"Cannot cancel task with status: {task['status']}"
        )

    # Update task status
    _thesis_tasks[task_id]["status"] = "cancelled"
    _thesis_tasks[task_id]["message"] = "Task cancelled by user"

    logger.info(f"[Thesis] Cancelled task {task_id}")

    return {"task_id": task_id, "status": "cancelled", "message": "Task cancelled"}


@router.get("/preview/{task_id}")
async def get_preview(task_id: str) -> dict:
    """Get thesis preview content.

    Returns the current LaTeX content for preview.
    """
    task = get_thesis_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "task_id": task_id,
        "latex_content": task.get("latex_content", ""),
        "sections_completed": task.get("sections_completed", 0),
        "sections_total": task.get("sections_total", 0),
    }
