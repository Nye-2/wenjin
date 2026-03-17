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
from src.application.handlers.feature_execution_handler import (
    FeatureExecutionHandler,
    get_feature_execution_handler,
    resolve_workspace_type,
)
from src.database import User
from src.gateway.routers.auth import get_current_user
from src.gateway.routers.workspaces import get_workspace_service
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
    taskType: str = "workspace_feature"
    handlerKey: str | None = None
    panel: str | None = None
    stages: list[FeatureStage] = Field(default_factory=list)
    color: str | None = None


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


def _feature_to_response(feature) -> WorkspaceFeature:
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

    workspace_type = resolve_workspace_type(workspace)
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

    result = await handler.execute(
        workspace_id, feature_id, request.params, request.thread_id,
        idempotency_key=idempotency_key,
        redis_client=runtime_redis,
    )
    return ExecuteResponse(**result)
