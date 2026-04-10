"""FastAPI routes for subagent operations."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_chat_thread_service
from src.services import ChatThreadService
from src.subagents import (
    GlobalSubagentManager,
    SubagentResult,
    SubagentStatus,
)
from src.subagents.manager import SubagentAccessError
from src.subagents.context_snapshot import build_subagent_context_snapshot
from src.subagents.runtime import get_manager
from src.subagents.task_builder import (
    SubagentRuntimeContext,
    build_subagent_metadata,
    build_subagent_task,
)

router = APIRouter(prefix="/subagents", tags=["subagents"])


class SpawnRequest(BaseModel):
    """Request to spawn a new subagent."""
    prompt: str
    subagent_type: str | None = None  # NEW: scout, writer, synthesizer, analyst
    tools: list[str] | None = None    # NEW: optional tool override
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
    result: SubagentResult | None = None


class CancelResponse(BaseModel):
    """Response after cancelling a task."""
    success: bool


@router.post("/threads/{thread_id}/spawn", response_model=SpawnResponse)
async def spawn_subagent(
    thread_id: str,
    request: SpawnRequest,
    current_user: User = Depends(get_current_user),
    manager: GlobalSubagentManager = Depends(get_manager),
    chat_thread_service: ChatThreadService = Depends(get_chat_thread_service),
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
    # Import academic resolver components
    from src.subagents.academic import (
        AcademicAgentResolver,
        InvalidToolError,
        UnknownSubagentTypeError,
        get_all_subagent_types,
    )

    # Resolve agent config if subagent_type specified
    system_prompt = None
    resolved_tools = None
    if manager._llm is None:
        raise HTTPException(
            status_code=503,
            detail="Subagent manager is unavailable because no chat model is configured.",
        )

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
            ) from e
        except InvalidToolError as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "InvalidTool",
                    "message": str(e),
                    "available_tools": e.available_tools,
                }
            ) from e

    thread = await chat_thread_service.get_thread(thread_id, str(current_user.id))
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    workspace_id = thread.workspace_id

    runtime_context = SubagentRuntimeContext(
        thread_id=thread_id,
        workspace_id=str(workspace_id) if workspace_id is not None else None,
        user_id=str(current_user.id),
    )
    context_snapshot = await build_subagent_context_snapshot(
        runtime_context=runtime_context,
        state=None,
    )

    task = build_subagent_task(
        manager._config,
        prompt=request.prompt,
        thread_id=thread_id,
        fallback_max_turns=request.max_turns,
        requested_max_turns=request.max_turns,
        requested_timeout=request.timeout,
        graph_template=request.graph_template,
        tools=resolved_tools if resolved_tools is not None else (request.tools or []),
        metadata=build_subagent_metadata(
            subagent_type=request.subagent_type,
            system_prompt=system_prompt,
            context_snapshot=context_snapshot,
            runtime_context=runtime_context,
            include_workspace=True,
            include_user=True,
        ),
    )
    try:
        await manager.spawn(task)
    except SubagentAccessError as exc:
        raise HTTPException(status_code=404, detail="Thread not found") from exc
    return SpawnResponse(task_id=task.task_id, status="pending")


@router.get(
    "/threads/{thread_id}/tasks/{task_id}/status",
    response_model=TaskStatusResponse,
)
async def get_task_status(
    thread_id: str,
    task_id: str,
    _current_user: User = Depends(get_current_user),
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
    status = await manager.get_status(thread_id, task_id, user_id=str(_current_user.id))
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")
    result = await manager.get_result(thread_id, task_id, user_id=str(_current_user.id))
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
    _current_user: User = Depends(get_current_user),
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
    success = await manager.cancel(thread_id, task_id, user_id=str(_current_user.id))
    return CancelResponse(success=success)


@router.get("/events")
async def subscribe_events(
    thread_id: str | None = None,
    _current_user: User = Depends(get_current_user),
    manager: GlobalSubagentManager = Depends(get_manager),
) -> StreamingResponse:
    """Subscribe to subagent event stream.

    Args:
        thread_id: Optional thread ID to filter events.
        manager: GlobalSubagentManager instance.

    Returns:
        StreamingResponse with SSE event stream.
    """
    if thread_id is not None:
        has_access = await manager.check_thread_access(thread_id, user_id=str(_current_user.id))
        if not has_access:
            raise HTTPException(status_code=404, detail="Thread not found")

    return StreamingResponse(
        manager.subscribe_events(thread_id, user_id=str(_current_user.id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
