"""Workspaces router for workspace management API endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from src.academic.services.paper_service import PaperService
from src.academic.services.workspace_service import WorkspaceService
from src.database import SubagentTaskRecord, TaskRecord, User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.contracts.paper import (
    paper_to_summary_response as paper_to_response,
)
from src.gateway.deps import (
    get_dashboard_service,
    get_db,
    get_paper_service,
    get_workspace_activity_service,
    get_workspace_service,
    get_workspace_summary_service,
)
from src.gateway.routers.workspaces_contracts import (
    AddPaperRequest,
    CreateWorkspaceRequest,
    ExecutionSessionResponse,
    PapersListResponse,
    UpdateWorkspaceRequest,
    WorkspaceActivityResponse,
    WorkspaceExecutionSessionsResponse,
    WorkspacePrismEnsureResponse,
    WorkspaceResponse,
    WorkspacesListResponse,
    WorkspaceSummaryResponse,
)
from src.gateway.routers.workspaces_runtime import (
    create_workspace_events_response_with_stream,
    get_owned_workspace,
    workspace_type_value,
)
from src.gateway.routers.workspaces_serializers import (
    workspace_activity_to_response,
    workspace_to_response,
)
from src.services.dashboard_service import DashboardService
from src.services.execution_session_events import serialize_execution_session
from src.services.execution_session_service import ExecutionSessionService
from src.services.thread_billing import (
    combine_token_usage,
    extract_persisted_metadata_usage,
    normalize_token_usage,
)
from src.services.workspace_activity_service import WorkspaceActivityService
from src.services.workspace_latex_projects import WorkspaceLatexProjectService
from src.services.workspace_summary_service import WorkspaceSummaryService
from src.workspace_events import stream_workspace_events

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _serialize_runtime_timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _subagent_event_time(record: SubagentTaskRecord) -> datetime:
    return record.completed_at or record.updated_at or record.created_at


def _serialize_subagent_record(record: SubagentTaskRecord) -> dict[str, Any]:
    metadata = (
        record.task_metadata
        if isinstance(record.task_metadata, dict)
        else {}
    )
    usage = extract_persisted_metadata_usage(metadata)
    model_name = metadata.get("model_name")
    return {
        "task_id": str(record.id),
        "thread_id": str(record.thread_id),
        "execution_session_id": str(record.execution_session_id).strip(),
        "status": record.status,
        "subagent_type": record.subagent_type,
        "workflow_phase": metadata.get("workflow_phase"),
        "workflow_phase_index": metadata.get("workflow_phase_index"),
        "workflow_task_index": metadata.get("workflow_task_index"),
        "workflow_strategy": metadata.get("workflow_strategy"),
        "output_preview": record.output_preview,
        "error": record.error,
        "token_usage": usage.as_dict() if usage is not None else None,
        "model_name": (
            str(model_name).strip()
            if isinstance(model_name, str) and model_name.strip()
            else None
        ),
        "updated_at": _serialize_runtime_timestamp(_subagent_event_time(record)),
    }


def _aggregate_subagent_token_usage(
    items: list[dict[str, Any]],
) -> dict[str, int] | None:
    usages = []
    for item in items:
        if not isinstance(item, dict):
            continue
        usage = normalize_token_usage(item.get("token_usage"))
        if usage is not None:
            usages.append(usage)
    combined = combine_token_usage(usages)
    return combined.as_dict() if combined is not None else None


async def _load_execution_enrichment(
    db: Any,
    sessions: list[Any],
) -> tuple[dict[str, TaskRecord], dict[str, list[dict[str, Any]]]]:
    serialized_sessions = [serialize_execution_session(session) for session in sessions]
    task_records_by_id: dict[str, TaskRecord] = {}
    subagents_by_execution: dict[str, list[dict[str, Any]]] = {
        str(session.get("id")): [] for session in serialized_sessions
    }

    try:
        task_ids = sorted(
            {
                task_id
                for session in serialized_sessions
                for task_id in [
                    str(session.get("primary_task_id") or "").strip(),
                    *[str(item).strip() for item in session.get("task_ids") or []],
                ]
                if task_id
            }
        )

        if task_ids:
            task_result = await db.execute(
                select(TaskRecord).where(TaskRecord.id.in_(task_ids))
            )
            task_records_by_id = {
                str(record.id): record for record in task_result.scalars().all()
            }

        execution_session_ids = sorted(
            {
                str(session.get("id") or "").strip()
                for session in serialized_sessions
                if str(session.get("id") or "").strip()
            }
        )
        if not execution_session_ids:
            return task_records_by_id, subagents_by_execution

        subagent_query = select(SubagentTaskRecord).where(
            SubagentTaskRecord.workspace_id == str(serialized_sessions[0].get("workspace_id") or ""),
            SubagentTaskRecord.execution_session_id.in_(execution_session_ids),
        )
        subagent_query = subagent_query.order_by(
            func.coalesce(
                SubagentTaskRecord.completed_at,
                SubagentTaskRecord.updated_at,
                SubagentTaskRecord.created_at,
            ).desc()
        )
        subagent_result = await db.execute(subagent_query)
        subagent_records = list(subagent_result.scalars().all())

        for record in subagent_records:
            execution_session_id = str(record.execution_session_id).strip()
            if execution_session_id not in subagents_by_execution:
                continue
            subagents_by_execution.setdefault(execution_session_id, []).append(
                _serialize_subagent_record(record)
            )

        for session_id, items in subagents_by_execution.items():
            items.sort(
                key=lambda item: str(item.get("updated_at") or ""),
                reverse=True,
            )
            subagents_by_execution[session_id] = items[:16]
    except Exception:
        return {}, subagents_by_execution

    return task_records_by_id, subagents_by_execution


async def _serialize_execution_session_response(
    session: Any,
    *,
    task_records_by_id: dict[str, TaskRecord],
    subagents_by_execution: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    payload = serialize_execution_session(session)
    try:
        task_record = None
        candidate_task_ids = [
            str(payload.get("primary_task_id") or "").strip(),
            *[str(item).strip() for item in payload.get("task_ids") or []],
        ]
        for task_id in candidate_task_ids:
            if task_id and task_id in task_records_by_id:
                task_record = task_records_by_id[task_id]
                break
        if task_record is not None:
            runtime_snapshot = payload.get("runtime_snapshot")
            current_step = None
            if isinstance(runtime_snapshot, dict):
                raw_current_step = runtime_snapshot.get("current_phase")
                if isinstance(raw_current_step, str) and raw_current_step.strip():
                    current_step = raw_current_step.strip()

            payload.update(
                {
                    "progress": task_record.progress,
                    "task_message": task_record.message,
                    "current_step": current_step,
                    "result_payload": task_record.result,
                }
            )

        payload["subagents"] = list(
            subagents_by_execution.get(str(payload.get("id")), [])
        )
        payload["token_usage"] = _aggregate_subagent_token_usage(payload["subagents"])
    except Exception:
        payload.setdefault("subagents", [])
        payload.setdefault("token_usage", None)
    return payload

@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    request: CreateWorkspaceRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    """Create a new workspace.

    Args:
        request: Workspace creation request
        current_user: Current authenticated user
        workspace_service: Workspace service instance

    Returns:
        Created workspace

    Raises:
        HTTPException: If workspace type is invalid
    """
    try:
        workspace = await workspace_service.create(
            user_id=str(current_user.id),
            name=request.name,
            type=request.type,
            discipline=request.discipline,
            description=request.description,
            config=request.config,
        )
        return workspace_to_response(workspace)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get("", response_model=WorkspacesListResponse)
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspacesListResponse:
    """List workspaces for current user.

    Args:
        current_user: Current authenticated user
        workspace_service: Workspace service instance

    Returns:
        List of workspaces for the user
    """
    workspaces = await workspace_service.list_by_user(str(current_user.id))
    return WorkspacesListResponse(
        workspaces=[workspace_to_response(w) for w in workspaces]
    )


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    """Get workspace by ID.

    Args:
        workspace_id: Workspace ID
        workspace_service: Workspace service instance

    Returns:
        Workspace details

    Raises:
        HTTPException: If workspace not found
    """
    workspace = await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    return workspace_to_response(workspace)


@router.post(
    "/{workspace_id}/prism/ensure",
    response_model=WorkspacePrismEnsureResponse,
)
async def ensure_workspace_prism_project(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: Any = Depends(get_db),
) -> WorkspacePrismEnsureResponse:
    """Ensure a workspace-linked WenjinPrism project exists."""
    workspace = await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    bridge_service = WorkspaceLatexProjectService(db)
    linked_project = await bridge_service.ensure_workspace_project(
        workspace_id=workspace_id,
        project_name=str(workspace.name or ""),
    )
    latex_project_id = str(linked_project.id)
    return WorkspacePrismEnsureResponse(
        latex_project_id=latex_project_id,
        url=f"/latex/{latex_project_id}",
        sync_status="ready",
    )


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    request: UpdateWorkspaceRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    """Update workspace.

    Args:
        workspace_id: Workspace ID
        request: Update request with fields to update
        workspace_service: Workspace service instance

    Returns:
        Updated workspace

    Raises:
        HTTPException: If workspace not found
    """
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    update_data = request.model_dump(exclude_unset=True)
    workspace = await workspace_service.update(workspace_id, **update_data)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    return workspace_to_response(workspace)


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, bool]:
    """Delete workspace.

    Args:
        workspace_id: Workspace ID
        workspace_service: Workspace service instance

    Returns:
        Success message

    Raises:
        HTTPException: If workspace not found
    """
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    success = await workspace_service.delete(workspace_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    return {"success": True}


@router.get("/{workspace_id}/papers", response_model=PapersListResponse)
async def list_workspace_papers(
    workspace_id: str,
    read_status: str | None = None,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    paper_service: PaperService = Depends(get_paper_service),
) -> PapersListResponse:
    """List papers in workspace.

    Args:
        workspace_id: Workspace ID
        read_status: Optional filter by read status
        paper_service: Paper service instance

    Returns:
        Papers in the workspace with total count
    """
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    papers = await paper_service.list_workspace_papers(
        workspace_id=workspace_id,
        read_status=read_status,
    )
    return PapersListResponse(
        papers=[paper_to_response(p, workspace_id=workspace_id) for p in papers],
        count=len(papers),
    )


@router.post("/{workspace_id}/papers/{paper_id}")
async def add_paper_to_workspace(
    workspace_id: str,
    paper_id: str,
    request: AddPaperRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    paper_service: PaperService = Depends(get_paper_service),
) -> dict[str, bool | str]:
    """Add paper to workspace.

    Args:
        workspace_id: Workspace ID
        paper_id: Paper ID to add
        request: Add paper request with optional notes and tags
        paper_service: Paper service instance

    Returns:
        Success message
    """
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    await paper_service.add_to_workspace(
        paper_id=paper_id,
        workspace_id=workspace_id,
        notes=request.notes,
        tags=request.tags,
        is_primary=request.is_primary,
    )
    return {"success": True, "paper_id": paper_id}


@router.delete("/{workspace_id}/papers/{paper_id}")
async def remove_paper_from_workspace(
    workspace_id: str,
    paper_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    paper_service: PaperService = Depends(get_paper_service),
) -> dict[str, bool]:
    """Remove paper from workspace.

    Args:
        workspace_id: Workspace ID
        paper_id: Paper ID to remove
        paper_service: Paper service instance

    Returns:
        Success message
    """
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    success = await paper_service.remove_from_workspace(
        paper_id=paper_id,
        workspace_id=workspace_id,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paper not found in workspace",
        )
    return {"success": True}


@router.get("/{workspace_id}/dashboard")
async def get_workspace_dashboard(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> dict[str, Any]:
    """Get workspace dashboard overview.

    Args:
        workspace_id: Workspace ID
        workspace_service: Workspace service instance
        dashboard_service: Dashboard service instance

    Returns:
        Dashboard with module statuses and recent artifacts

    Raises:
        HTTPException: If workspace not found
    """
    workspace = await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    try:
        workspace_type = workspace_type_value(workspace)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return await dashboard_service.get_dashboard(
        workspace_id,
        workspace_type=workspace_type,
    )


@router.get("/{workspace_id}/summary", response_model=WorkspaceSummaryResponse)
async def get_workspace_summary(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    summary_service: WorkspaceSummaryService = Depends(get_workspace_summary_service),
) -> WorkspaceSummaryResponse:
    """Get workspace cockpit summary with phase, recommendation, and risk data."""
    workspace = await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    try:
        workspace_type = workspace_type_value(workspace)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    payload = await summary_service.get_summary(
        workspace_id,
        workspace_type=workspace_type,
        user_id=str(current_user.id),
    )
    return WorkspaceSummaryResponse(**payload)


@router.get("/{workspace_id}/activity", response_model=WorkspaceActivityResponse)
async def get_workspace_activity(
    workspace_id: str,
    limit: int = 40,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    activity_service: WorkspaceActivityService = Depends(get_workspace_activity_service),
) -> WorkspaceActivityResponse:
    """Get a unified recent activity timeline for the workspace."""
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    activity = await activity_service.get_activity(
        workspace_id,
        user_id=str(current_user.id),
        limit=limit,
    )
    return WorkspaceActivityResponse(
        items=[workspace_activity_to_response(item) for item in activity["items"]],
        count=int(activity.get("count", 0)),
    )


@router.get(
    "/{workspace_id}/executions",
    response_model=WorkspaceExecutionSessionsResponse,
)
async def list_workspace_execution_sessions(
    workspace_id: str,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceExecutionSessionsResponse:
    """List converged execution sessions for a workspace."""
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    from src.database import get_db_session

    async with get_db_session() as db:
        service = ExecutionSessionService(db)
        items = await service.list_workspace_sessions(
            workspace_id=workspace_id,
            user_id=str(current_user.id),
            limit=limit,
        )
        task_records_by_id, subagents_by_execution = await _load_execution_enrichment(
            db,
            items,
        )
        serialized_items = [
            ExecutionSessionResponse(
                **(
                    await _serialize_execution_session_response(
                        item,
                        task_records_by_id=task_records_by_id,
                        subagents_by_execution=subagents_by_execution,
                    )
                )
            )
            for item in items
        ]
    return WorkspaceExecutionSessionsResponse(
        items=serialized_items,
        count=len(items),
    )


@router.get("/{workspace_id}/events")
async def subscribe_workspace_events(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> StreamingResponse:
    """Subscribe to workspace-scoped live events via SSE."""
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    return await create_workspace_events_response_with_stream(
        workspace_id=workspace_id,
        stream_factory=stream_workspace_events,
    )
