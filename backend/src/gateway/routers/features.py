"""Features router for workspace feature discovery and execution.

This router is a thin HTTP adapter. Business orchestration (credit billing,
literature threshold checks, task submission, failure compensation) lives in
``application.handlers.feature_execution_handler``.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from src.academic.services.workspace_service import WorkspaceService
from src.application.errors import ApplicationError
from src.application.handlers.feature_execution_handler import FeatureExecutionHandler, resolve_workspace_type
from src.application.results import FeatureExecutionAdvisory, FeatureTaskSubmission
from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_feature_execution_handler, get_workspace_service
from src.gateway.error_mapping import to_http_exception
from src.task.registry import WORKSPACE_FEATURE_TASK
from src.workspace_features import list_workspace_features

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


class FeaturesResponse(BaseModel):
    """Response for features list."""

    features: list[WorkspaceFeature]


class ExecuteRequest(BaseModel):
    """Request to execute a feature."""

    params: dict[str, Any] = Field(default_factory=dict)
    thread_id: str | None = None


class ExecuteResponse(BaseModel):
    """Response for feature execution."""

    task_id: str | None = None
    status: str
    feature_id: str
    message: str
    warning: str | None = None
    detail: dict[str, Any] | None = None


# ============ Helpers ============


def _feature_to_response(feature: Any) -> WorkspaceFeature:
    """Convert registry definitions to the public API model."""
    return WorkspaceFeature(**feature.to_api_dict())


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
    handler: FeatureExecutionHandler = Depends(get_feature_execution_handler),
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
        result = await handler.execute(
            workspace_id, feature_id, request.params, request.thread_id,
            idempotency_key=idempotency_key,
            redis_client=runtime_redis,
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc

    if isinstance(result, FeatureTaskSubmission):
        return ExecuteResponse(
            task_id=result.task_id,
            status="pending",
            feature_id=result.feature_id,
            message=result.message,
            warning=None,
            detail=None,
        )

    if isinstance(result, FeatureExecutionAdvisory):
        return ExecuteResponse(
            task_id=None,
            status="warning",
            feature_id=result.feature_id,
            message=result.message,
            warning=result.code,
            detail=result.context,
        )

    return ExecuteResponse(
        task_id=result.get("task_id"),
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
