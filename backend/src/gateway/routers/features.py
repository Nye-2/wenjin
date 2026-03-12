"""Features router for workspace feature discovery and execution."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.academic.services.workspace_service import WorkspaceService
from src.database import User
from src.gateway.routers.auth import get_current_user
from src.gateway.routers.tasks import get_task_service
from src.gateway.routers.workspaces import get_workspace_service
from src.services.literature_service import LiteratureService, get_literature_service
from src.task.service import TaskService
from src.workspace_features import get_workspace_feature, list_workspace_features

logger = logging.getLogger(__name__)

router = APIRouter(tags=["features"])

# Recommended minimum literature count for thesis writing
LITERATURE_THRESHOLD = 15


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


def _resolve_workspace_type(workspace: Any) -> str:
    """Normalize workspace.type across enum and string shapes."""
    workspace_type = getattr(workspace, "type", None)
    if workspace_type is None:
        return "thesis"
    return workspace_type.value if hasattr(workspace_type, "value") else str(workspace_type)


def _feature_to_response(feature) -> WorkspaceFeature:
    """Convert registry definitions to the public API model."""
    return WorkspaceFeature(**feature.to_api_dict())


def _build_task_payload(
    *,
    workspace: Any,
    workspace_id: str,
    workspace_type: str,
    feature,
    request: ExecuteRequest,
) -> dict[str, Any]:
    """Build the canonical task payload for workspace feature execution."""
    payload = dict(request.params)
    payload.update(
        {
            "workspace_id": workspace_id,
            "workspace_type": workspace_type,
            "workspace_name": getattr(workspace, "name", ""),
            "workspace_description": getattr(workspace, "description", ""),
            "workspace_discipline": getattr(workspace, "discipline", ""),
            "workspace_config": getattr(workspace, "config", {}) or {},
            "feature_id": feature.id,
            "feature_name": feature.name,
            "agent": feature.agent,
            "agent_label": feature.agent_label,
            "handler_key": feature.handler_key,
            "thread_id": request.thread_id,
            "params": request.params,
        }
    )
    return payload


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

    workspace_type = _resolve_workspace_type(workspace)
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
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    task_service: TaskService = Depends(get_task_service),
    literature_service: LiteratureService = Depends(get_literature_service),
) -> ExecuteResponse:
    """Execute a feature for a workspace via the unified task infrastructure."""
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    workspace_type = _resolve_workspace_type(workspace)
    feature = get_workspace_feature(workspace_type, feature_id)
    if not feature:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_id}' not found for workspace type '{workspace_type}'",
        )

    # Check literature sufficiency for thesis writing
    if feature_id == "thesis_writing":
        action = request.params.get("action", "write_all") if request.params else "write_all"
        if action in ("write_chapter", "write_all"):
            lit_stats = await literature_service.count_literature(workspace_id)
            if lit_stats["total"] < LITERATURE_THRESHOLD:
                return ExecuteResponse(
                    task_id=None,
                    status="warning",
                    feature_id=feature_id,
                    message="文献数量不足，建议先补充文献",
                    warning="literature_insufficient",
                    detail={"current": lit_stats["total"], "recommended": LITERATURE_THRESHOLD},
                )

    task_id = await task_service.submit_task(
        user_id=str(current_user.id),
        task_type=feature.task_type,
        payload=_build_task_payload(
            workspace=workspace,
            workspace_id=workspace_id,
            workspace_type=workspace_type,
            feature=feature,
            request=request,
        ),
    )

    logger.info(
        "[Features] Started %s task %s for workspace %s",
        feature_id,
        task_id,
        workspace_id,
    )

    return ExecuteResponse(
        task_id=task_id,
        status="pending",
        feature_id=feature_id,
        message=f"Queued {feature.name}",
    )
