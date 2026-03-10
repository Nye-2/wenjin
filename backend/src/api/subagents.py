"""FastAPI routes for subagent operations."""

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.subagents import (
    GlobalSubagentManager,
    SubagentTask,
    SubagentStatus,
    SubagentResult,
)


router = APIRouter(prefix="/subagents", tags=["subagents"])


class SpawnRequest(BaseModel):
    """Request to spawn a new subagent."""
    prompt: str
    subagent_type: Optional[str] = None  # NEW: scout, writer, synthesizer, analyst
    tools: Optional[list[str]] = None    # NEW: optional tool override
    max_turns: int = 10
    timeout: int = 900
    graph_template: str = "default"


class SpawnResponse(BaseModel):
    """Response after spawning a subagent."""
    task_id: str
    status: str


class TaskStatusResponse(BaseModel):
    """Response with task status."""
    task_id: str
    thread_id: str
    status: SubagentStatus
    result: Optional[SubagentResult] = None


class CancelResponse(BaseModel):
    """Response after cancelling a task."""
    success: bool


def get_manager() -> GlobalSubagentManager:
    """Get the GlobalSubagentManager instance."""
    return GlobalSubagentManager.get_instance()


@router.post("/threads/{thread_id}/spawn", response_model=SpawnResponse)
async def spawn_subagent(
    thread_id: str,
    request: SpawnRequest,
    manager: GlobalSubagentManager = Depends(get_manager),
) -> SpawnResponse:
    """Spawn a new subagent task.

    Args:
        thread_id: Thread ID for the task.
        request: Spawn request parameters.
        manager: GlobalSubagentManager instance.

    Returns:
        SpawnResponse with task ID and initial status.

    Raises:
        HTTPException: If subagent_type is unknown or tools are invalid.
    """
    from datetime import datetime

    # Import academic resolver components
    from src.subagents.academic import (
        AcademicAgentResolver,
        UnknownSubagentTypeError,
        InvalidToolError,
        get_all_subagent_types,
    )

    # Resolve agent config if subagent_type specified
    system_prompt = None
    resolved_tools = None
    if request.subagent_type:
        resolver = AcademicAgentResolver(manager._tools)
        try:
            config = resolver.resolve_config(request.subagent_type, request.tools)
            system_prompt = config.system_prompt
            resolved_tools = config.tools
        except UnknownSubagentTypeError as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "UnknownSubagentType",
                    "message": str(e),
                    "valid_types": get_all_subagent_types(),
                }
            )
        except InvalidToolError as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "InvalidTool",
                    "message": str(e),
                    "available_tools": e.available_tools,
                }
            )

    task = SubagentTask(
        task_id=str(uuid4()),
        thread_id=thread_id,
        prompt=request.prompt,
        created_at=datetime.now(),
        max_turns=min(request.max_turns, manager._config.max_turns_limit),
        timeout=min(request.timeout, manager._config.max_timeout),
        graph_template=request.graph_template,
        tools=resolved_tools if resolved_tools is not None else (request.tools or []),
        metadata={
            "subagent_type": request.subagent_type,
            "system_prompt": system_prompt,
        }
    )
    await manager.spawn(task)
    return SpawnResponse(task_id=task.task_id, status="pending")


@router.get(
    "/threads/{thread_id}/tasks/{task_id}/status",
    response_model=TaskStatusResponse,
)
async def get_task_status(
    thread_id: str,
    task_id: str,
    manager: GlobalSubagentManager = Depends(get_manager),
) -> TaskStatusResponse:
    """Get the status of a subagent task.

    Args:
        thread_id: Thread ID.
        task_id: Task ID.
        manager: GlobalSubagentManager instance.

    Returns:
        TaskStatusResponse with status and optional result.

    Raises:
        HTTPException: If task not found.
    """
    status = await manager.get_status(thread_id, task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")
    result = await manager.get_result(thread_id, task_id)
    return TaskStatusResponse(
        task_id=task_id,
        thread_id=thread_id,
        status=status,
        result=result,
    )


@router.post(
    "/threads/{thread_id}/tasks/{task_id}/cancel",
    response_model=CancelResponse,
)
async def cancel_task(
    thread_id: str,
    task_id: str,
    manager: GlobalSubagentManager = Depends(get_manager),
) -> CancelResponse:
    """Cancel a running subagent task.

    Args:
        thread_id: Thread ID.
        task_id: Task ID.
        manager: GlobalSubagentManager instance.

    Returns:
        CancelResponse with success status.
    """
    success = await manager.cancel(thread_id, task_id)
    return CancelResponse(success=success)


@router.get("/events")
async def subscribe_events(
    thread_id: Optional[str] = None,
    manager: GlobalSubagentManager = Depends(get_manager),
) -> StreamingResponse:
    """Subscribe to subagent event stream.

    Args:
        thread_id: Optional thread ID to filter events.
        manager: GlobalSubagentManager instance.

    Returns:
        StreamingResponse with SSE event stream.
    """
    return StreamingResponse(
        manager.subscribe_events(thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
