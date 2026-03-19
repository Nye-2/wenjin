"""Task API router."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_task_service
from src.services.feature_credit_policy import BILLABLE_TASK_TYPES
from src.task.service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


# === Request/Response Models ===

class TaskSubmitRequest(BaseModel):
    """Task submission request."""
    task_type: str = Field(..., description="Type of task to execute")
    priority: int = Field(5, ge=1, le=10, description="Task priority (1-10)")
    payload: dict = Field(..., description="Task-specific parameters")


class TaskSubmitResponse(BaseModel):
    """Task submission response."""
    task_id: str
    status: str = "pending"


class TaskStatusResponse(BaseModel):
    """Task status response."""
    task_id: str
    task_type: str
    status: str
    progress: int
    message: str | None = None
    result: dict | None = None
    error: str | None = None
    metadata: dict | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class TaskListResponse(BaseModel):
    """Task list response."""
    tasks: list[TaskStatusResponse]
    count: int


# === Dependencies ===

async def get_current_user_id(current_user: User = Depends(get_current_user)) -> str:
    """Get current authenticated user ID."""
    return str(current_user.id)


# === Endpoints ===

@router.post("", response_model=TaskSubmitResponse, status_code=201)
async def submit_task(
    request: TaskSubmitRequest,
    user_id: str = Depends(get_current_user_id),
    task_service: TaskService = Depends(get_task_service),
):
    """Submit a new async task."""
    if request.task_type in BILLABLE_TASK_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Task type '{request.task_type}' must be started from workspace feature "
                "execution endpoints to ensure credit accounting."
            ),
        )

    try:
        task_id = await task_service.submit_task(
            user_id=user_id,
            task_type=request.task_type,
            payload=request.payload,
            priority=request.priority,
        )
        return TaskSubmitResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    task_service: TaskService = Depends(get_task_service),
):
    """Get task status."""
    status = await task_service.get_task_status(task_id, user_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(**status)


@router.get("/{task_id}/stream")
async def stream_task_progress(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    task_service: TaskService = Depends(get_task_service),
):
    """Stream task progress via SSE."""
    # Verify access
    status = await task_service.get_task_status(task_id, user_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")

    from src.task.sse import create_task_sse_stream
    return StreamingResponse(
        create_task_sse_stream(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    status: str | None = Query(None, description="Filter by status"),
    task_type: str | None = Query(None, description="Filter by task type"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    user_id: str = Depends(get_current_user_id),
    task_service: TaskService = Depends(get_task_service),
):
    """List tasks for current user."""
    tasks = await task_service.list_tasks(
        user_id=user_id,
        status=status,
        task_type=task_type,
        limit=limit,
    )
    return TaskListResponse(
        tasks=[TaskStatusResponse(**t) for t in tasks],
        count=len(tasks),
    )


@router.delete("/{task_id}")
async def cancel_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    task_service: TaskService = Depends(get_task_service),
):
    """Cancel a task."""
    success = await task_service.cancel_task(task_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or cannot be cancelled")
    return {"success": True, "task_id": task_id}
