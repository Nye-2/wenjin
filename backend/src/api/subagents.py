"""FastAPI routes for subagent operations."""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.subagents import (
    GlobalSubagentManager,
    SubagentTask,
    SubagentStatus,
    SubagentResult,
)
from src.subagents.manager import SubagentAccessError


logger = logging.getLogger(__name__)

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


def _build_default_manager_config():
    """Build a default subagent manager configuration lazily."""
    from src.subagents.config import SubagentConfig

    config = SubagentConfig.from_env()

    try:
        from src.config import get_default_model_id
        from src.models.factory import create_chat_model

        config.llm = create_chat_model(get_default_model_id())
    except Exception as exc:
        logger.warning("Failed to initialize default subagent model: %s", exc)
        config.llm = None

    try:
        from src.agents.lead_agent.agent import get_available_tools

        config.default_tools = get_available_tools(subagent_enabled=False)
    except Exception as exc:
        logger.warning("Failed to initialize default subagent tools: %s", exc)
        config.default_tools = []

    return config


def get_manager() -> GlobalSubagentManager:
    """Get the GlobalSubagentManager instance."""
    try:
        return GlobalSubagentManager.get_instance()
    except RuntimeError:
        try:
            return GlobalSubagentManager.initialize(_build_default_manager_config())
        except RuntimeError:
            return GlobalSubagentManager.get_instance()


@router.post("/threads/{thread_id}/spawn", response_model=SpawnResponse)
async def spawn_subagent(
    thread_id: str,
    request: SpawnRequest,
    current_user: User = Depends(get_current_user),
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

    task = SubagentTask(
        task_id=str(uuid4()),
        thread_id=thread_id,
        prompt=request.prompt,
        created_at=datetime.now(UTC),
        max_turns=min(request.max_turns, manager._config.max_turns_limit),
        timeout=min(request.timeout, manager._config.max_timeout),
        graph_template=request.graph_template,
        tools=resolved_tools if resolved_tools is not None else (request.tools or []),
        metadata={
            "subagent_type": request.subagent_type,
            "system_prompt": system_prompt,
            "user_id": str(current_user.id),
        }
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
