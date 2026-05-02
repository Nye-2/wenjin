"""Features router for workspace feature discovery and execution.

This router is a thin HTTP adapter. Launch orchestration (literature threshold
checks, task submission, idempotency) lives in
``application.services.feature_submission_service``. Feature billing is settled
after task completion from measured token usage.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from src.academic.services.artifact_service import ArtifactService
from src.academic.services.workspace_service import WorkspaceService
from src.application.commands import FeatureLaunchCommand
from src.application.errors import ApplicationError
from src.application.results import FeatureExecutionAdvisory, FeatureTaskSubmission
from src.application.services import FeatureIngressService
from src.application.workspace_resolvers import resolve_workspace_type
from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_feature_launch_service, get_workspace_service
from src.gateway.deps.core import get_db
from src.gateway.error_mapping import to_http_exception
from src.services.feature_action_resolution_service import resolve_feature_action_state
from src.task.registry import WORKSPACE_FEATURE_TASK
from src.workspace_features import get_workspace_feature, list_workspace_features
from src.workspace_features.skills import get_default_skill_for_feature

logger = logging.getLogger(__name__)

router = APIRouter(tags=["features"])


# ============ Request/Response Models ============


class FeatureStage(BaseModel):
    """A stage in feature execution."""

    id: str
    label: str


class WorkspaceFeature(BaseModel):
    """A feature available in a workspace."""

    id: str
    name: str
    description: str
    icon: str
    agent: str
    agentLabel: str
    taskType: str = WORKSPACE_FEATURE_TASK
    handlerKey: str | None = None
    panel: str | None = None
    stages: list[FeatureStage] = Field(default_factory=list)
    color: str | None = None
    followUpPrompt: str | None = None
    defaultSkillId: str | None = None


class FeaturesResponse(BaseModel):
    """Response for features list."""

    features: list[WorkspaceFeature]


class ExecuteRequest(BaseModel):
    """Request to execute a feature."""

    params: dict[str, Any] = Field(default_factory=dict)
    thread_id: str | None = None
    skill_id: str | None = None
    execution_session_id: str | None = None


class ExecuteResponse(BaseModel):
    """Response for feature execution."""

    task_id: str | None = None
    execution_session_id: str | None = None
    status: str
    feature_id: str
    message: str
    warning: str | None = None
    detail: dict[str, Any] | None = None


class ResolveActionRequest(BaseModel):
    """Request to resolve feature action state."""

    orchestration_params: dict[str, Any] | None = Field(default=None)
    source_artifact_id: str | None = Field(default=None)


class ResolveActionResponse(BaseModel):
    """Response for feature action resolution."""

    source_artifact_id: str | None = None
    follow_up_prompt: str
    route_params: dict[str, Any]
    rerun_params: dict[str, Any] | None = None
    rerun_unavailable_reason: str | None = None


# ============ Helpers ============


def _feature_to_response(feature: Any) -> WorkspaceFeature:
    """Convert registry definitions to the public API model."""
    payload = feature.to_api_dict()
    payload["defaultSkillId"] = get_default_skill_for_feature(
        feature.workspace_type,
        feature.id,
    )
    return WorkspaceFeature(**payload)


# ============ Endpoints ============


@router.get(
    "/workspaces/{workspace_id}/features",
    response_model=FeaturesResponse,
)
async def get_workspace_features(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> FeaturesResponse:
    """Get available features for a workspace."""
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        workspace_type = resolve_workspace_type(workspace)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    features = [
        _feature_to_response(feature)
        for feature in list_workspace_features(workspace_type)
    ]
    return FeaturesResponse(features=features)


@router.post(
    "/workspaces/{workspace_id}/features/{feature_id}/execute",
    response_model=ExecuteResponse,
)
async def execute_feature(
    workspace_id: str,
    feature_id: str,
    request: ExecuteRequest,
    launch_service: FeatureIngressService = Depends(get_feature_launch_service),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> ExecuteResponse:
    """Execute a feature for a workspace via the unified task infrastructure."""
    # Always provide Redis client so distributed workspace lock can be applied.
    from src.academic.cache.redis_client import redis_client
    from src.config import redis_settings

    runtime_redis = (
        redis_client
        if redis_settings.enabled and redis_client._client is not None
        else None
    )

    try:
        launch = await launch_service.launch(
            FeatureLaunchCommand(
                workspace_id=workspace_id,
                feature_id=feature_id,
                params=request.params,
                thread_id=request.thread_id,
                skill_id=request.skill_id,
                launch_source="panel",
                idempotency_key=idempotency_key,
                redis_client=runtime_redis,
                execution_session_id=request.execution_session_id,
            )
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc

    result = launch.outcome
    if isinstance(result, FeatureTaskSubmission):
        return ExecuteResponse(
            task_id=result.task_id,
            execution_session_id=launch.execution_session_id,
            status="pending",
            feature_id=result.feature_id,
            message=result.message,
            warning=None,
            detail=None,
        )

    if isinstance(result, FeatureExecutionAdvisory):
        return ExecuteResponse(
            task_id=None,
            execution_session_id=launch.execution_session_id,
            status=(
                "awaiting_user_input"
                if result.code == "missing_params"
                else "warning"
            ),
            feature_id=result.feature_id,
            message=result.message,
            warning=result.code,
            detail=result.context,
        )

    return ExecuteResponse(
        task_id=result.get("task_id"),
        execution_session_id=launch.execution_session_id,
        status=str(result.get("status", "success")),
        feature_id=str(result.get("feature_id", feature_id)),
        message=str(result.get("message", "")),
        warning=(
            str(result["warning"])
            if result.get("warning") is not None
            else None
        ),
        detail=result.get("detail") if isinstance(result.get("detail"), dict) else None,
    )


@router.post(
    "/workspaces/{workspace_id}/features/{feature_id}/resolve-action",
    response_model=ResolveActionResponse,
)
async def resolve_feature_action(
    workspace_id: str,
    feature_id: str,
    request: ResolveActionRequest,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: AsyncSession = Depends(get_db),
) -> ResolveActionResponse:
    """Resolve feature action state for a workspace feature.

    Computes route_params, rerun_params, and rerun availability based on
    workspace state, artifacts, and orchestration parameters.
    """
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        workspace_type = resolve_workspace_type(workspace)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    feature_def = get_workspace_feature(workspace_type, feature_id)
    if feature_def is None:
        raise HTTPException(status_code=404, detail="Feature not found")
    follow_up_prompt = feature_def.follow_up_prompt

    artifact_service = ArtifactService(db)
    artifacts = await artifact_service.list_by_workspace(workspace_id)

    state = resolve_feature_action_state(
        feature_id=feature_id,
        workspace=workspace,
        artifacts=artifacts,
        orchestration_params=request.orchestration_params,
        explicit_source_artifact_id=request.source_artifact_id,
        follow_up_prompt=follow_up_prompt,
    )

    return ResolveActionResponse(
        source_artifact_id=state.get("source_artifact_id"),
        follow_up_prompt=state["follow_up_prompt"],
        route_params=state["route_params"],
        rerun_params=state.get("rerun_params"),
        rerun_unavailable_reason=state.get("rerun_unavailable_reason"),
    )
