"""Task API router for task status, streaming, listing, and cancellation."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_task_service
from src.task.service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskStatusResponse(BaseModel):
    """Task status response."""
    task_id: str
    task_type: str
    status: str
    progress: int
    message: str | None = None
    current_step: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None
    workspace_id: str | None = None
    feature_id: str | None = None
    thread_id: str | None = None
    action: str | None = None
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


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    task_service: TaskService = Depends(get_task_service),
) -> TaskStatusResponse:
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
) -> StreamingResponse:
    """Stream task progress via SSE."""
    # Verify access
    status = await task_service.get_task_status(task_id, user_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")

    from src.task.sse import TaskEventStreamUnavailable, create_task_sse_stream
    try:
        stream = await create_task_sse_stream(task_id)
    except TaskEventStreamUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Task event stream is temporarily unavailable",
        ) from exc
    return StreamingResponse(
        stream,
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
    workspace_id: str | None = Query(None, description="Filter by workspace"),
    feature_id: str | None = Query(None, description="Filter by feature"),
    action: str | None = Query(None, description="Filter by action"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    user_id: str = Depends(get_current_user_id),
    task_service: TaskService = Depends(get_task_service),
) -> TaskListResponse:
    """List tasks for current user."""
    tasks = await task_service.list_tasks(
        user_id=user_id,
        status=status,
        task_type=task_type,
        limit=limit,
        workspace_id=workspace_id,
        feature_id=feature_id,
        action=action,
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
) -> dict[str, bool | str]:
    """Cancel a task."""
    success = await task_service.cancel_task(task_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or cannot be cancelled")
    return {"success": True, "task_id": task_id}
