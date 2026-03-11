"""Features router for workspace features API endpoints.

This module provides the GET /workspaces/{workspace_id}/features endpoint
that returns available features for a workspace based on its type.

Features are the pluggable building blocks that define what functionality
is available in a workspace. The frontend uses this to dynamically render
QuickActions, AgentStatusBar, and FeaturePanels.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import User, get_db_session
from src.gateway.routers.auth import get_current_user
from src.gateway.routers.workspaces import get_workspace_service, get_db
from src.academic.services.workspace_service import WorkspaceService

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
    panel: str | None = None
    stages: list[FeatureStage] = []
    color: str | None = None


class FeaturesResponse(BaseModel):
    """Response for features list."""
    features: list[WorkspaceFeature]


# ============ Feature Definitions ============
# Features are organized by workspace type

THESIS_FEATURES = [
    WorkspaceFeature(
        id="outline",
        name="生成大纲",
        description="根据研究主题生成论文大纲",
        icon="list",
        agent="thesis_writer",
        agentLabel="ThesisWriter",
        panel="outline_editor",
        color="purple",
        stages=[
            FeatureStage(id="analyze", label="分析需求"),
            FeatureStage(id="generate", label="生成大纲"),
            FeatureStage(id="refine", label="优化调整"),
        ],
    ),
    WorkspaceFeature(
        id="literature",
        name="文献综述",
        description="搜索和整理相关文献",
        icon="book",
        agent="librarian",
        agentLabel="Librarian",
        panel="literature_panel",
        color="emerald",
        stages=[
            FeatureStage(id="search", label="搜索文献"),
            FeatureStage(id="analyze", label="分析文献"),
            FeatureStage(id="synthesize", label="综合整理"),
        ],
    ),
    WorkspaceFeature(
        id="chapter",
        name="章节写作",
        description="生成论文章节内容",
        icon="pen",
        agent="thesis_writer",
        agentLabel="ThesisWriter",
        panel="chapter_editor",
        color="amber",
        stages=[
            FeatureStage(id="outline", label="规划结构"),
            FeatureStage(id="write", label="撰写内容"),
            FeatureStage(id="revise", label="修订完善"),
        ],
    ),
    WorkspaceFeature(
        id="figure",
        name="图表规划",
        description="规划和生成论文图表",
        icon="chart",
        agent="figure_planner",
        agentLabel="FigurePlanner",
        panel="figure_panel",
        color="rose",
        stages=[
            FeatureStage(id="analyze", label="分析需求"),
            FeatureStage(id="design", label="设计方案"),
            FeatureStage(id="generate", label="生成图表"),
        ],
    ),
    WorkspaceFeature(
        id="compile",
        name="编译预览",
        description="编译 LaTeX 并生成 PDF 预览",
        icon="file",
        agent="thesis_writer",
        agentLabel="ThesisWriter",
        panel="latex_preview",
        color="blue",
        stages=[
            FeatureStage(id="compile", label="编译 LaTeX"),
            FeatureStage(id="preview", label="生成预览"),
        ],
    ),
    WorkspaceFeature(
        id="export",
        name="导出论文",
        description="导出完整的论文 PDF",
        icon="download",
        agent="thesis_writer",
        agentLabel="ThesisWriter",
        panel=None,
        color="indigo",
        stages=[
            FeatureStage(id="prepare", label="准备文档"),
            FeatureStage(id="export", label="导出文件"),
        ],
    ),
]

SCI_FEATURES = [
    WorkspaceFeature(
        id="literature_search",
        name="文献检索",
        description="检索相关学术文献",
        icon="search",
        agent="scout",
        agentLabel="Scout",
        panel="literature_panel",
        color="emerald",
        stages=[
            FeatureStage(id="search", label="检索文献"),
            FeatureStage(id="filter", label="筛选结果"),
        ],
    ),
    WorkspaceFeature(
        id="paper_analysis",
        name="论文分析",
        description="分析论文结构和方法",
        icon="flask",
        agent="analyst",
        agentLabel="Analyst",
        panel="analysis_panel",
        color="purple",
        stages=[
            FeatureStage(id="parse", label="解析论文"),
            FeatureStage(id="analyze", label="深度分析"),
            FeatureStage(id="summarize", label="生成摘要"),
        ],
    ),
    WorkspaceFeature(
        id="writing",
        name="论文写作",
        description="撰写学术论文内容",
        icon="pen",
        agent="writer",
        agentLabel="Writer",
        panel="editor_panel",
        color="amber",
        stages=[
            FeatureStage(id="plan", label="规划结构"),
            FeatureStage(id="write", label="撰写内容"),
            FeatureStage(id="revise", label="修订完善"),
        ],
    ),
]

PROPOSAL_FEATURES = [
    WorkspaceFeature(
        id="proposal_outline",
        name="申报书大纲",
        description="生成项目申报书大纲",
        icon="list",
        agent="writer",
        agentLabel="Writer",
        panel="outline_editor",
        color="purple",
        stages=[
            FeatureStage(id="analyze", label="分析要求"),
            FeatureStage(id="generate", label="生成大纲"),
        ],
    ),
    WorkspaceFeature(
        id="background_research",
        name="背景调研",
        description="调研项目背景和现状",
        icon="book",
        agent="scout",
        agentLabel="Scout",
        panel="literature_panel",
        color="emerald",
        stages=[
            FeatureStage(id="search", label="搜索资料"),
            FeatureStage(id="summarize", label="整理归纳"),
        ],
    ),
]

# Map workspace types to their features
WORKSPACE_FEATURES: dict[str, list[WorkspaceFeature]] = {
    "thesis": THESIS_FEATURES,
    "sci": SCI_FEATURES,
    "proposal": PROPOSAL_FEATURES,
    "grant": PROPOSAL_FEATURES,  # Similar to proposal
    "literature_review": SCI_FEATURES[:1],  # Just literature search
}


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
    """Get available features for a workspace.

    Returns the list of features available for this workspace based on its type.
    The frontend uses this to dynamically render QuickActions and panels.

    Args:
        workspace_id: The workspace ID
        current_user: Current authenticated user
        workspace_service: Workspace service instance

    Returns:
        FeaturesResponse with list of available features

    Raises:
        HTTPException: 404 if workspace not found, 403 if access denied
    """
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found",
        )

    # Verify workspace ownership
    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="Access denied",
        )

    # Get workspace type
    workspace_type = workspace.type.value if workspace.type else "thesis"

    # Get features for this workspace type
    features = WORKSPACE_FEATURES.get(workspace_type, [])

    return FeaturesResponse(features=features)


# ============ Execute Feature ============

class ExecuteRequest(BaseModel):
    """Request to execute a feature."""
    params: dict[str, Any] = {}
    thread_id: str | None = None


class ExecuteResponse(BaseModel):
    """Response for feature execution."""
    task_id: str
    status: str
    feature_id: str
    message: str


def _get_feature_by_id(workspace_type: str, feature_id: str) -> WorkspaceFeature | None:
    """Get feature configuration by workspace type and feature ID."""
    features = WORKSPACE_FEATURES.get(workspace_type, [])
    for f in features:
        if f.id == feature_id:
            return f
    return None


@router.post(
    "/workspaces/{workspace_id}/features/{feature_id}/execute",
    response_model=ExecuteResponse,
)
async def execute_feature(
    workspace_id: str,
    feature_id: str,
    request: ExecuteRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> ExecuteResponse:
    """Execute a feature for a workspace.

    This endpoint:
    1. Validates the feature exists for this workspace type
    2. Creates a task for tracking
    3. Executes the feature in background
    4. Returns task_id for status polling

    Args:
        workspace_id: The workspace ID
        feature_id: The feature ID to execute
        request: Execution parameters
        background_tasks: FastAPI background tasks
        current_user: Current authenticated user
        workspace_service: Workspace service instance

    Returns:
        ExecuteResponse with task_id and initial status

    Raises:
        HTTPException: 404 if workspace or feature not found, 403 if access denied
    """
    # Get workspace
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found",
        )

    # Verify workspace ownership
    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="Access denied",
        )

    # Get workspace type and feature config
    # Handle both enum and string type
    workspace_type = workspace.type.value if hasattr(workspace.type, 'value') else str(workspace.type) if workspace.type else "thesis"
    feature = _get_feature_by_id(workspace_type, feature_id)

    if not feature:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_id}' not found for workspace type '{workspace_type}'",
        )

    # Create task based on feature type
    task_id = await _create_and_start_task(
        workspace_id=workspace_id,
        feature=feature,
        params=request.params,
        background_tasks=background_tasks,
        user_id=str(current_user.id),
    )

    logger.info(f"[Features] Started {feature_id} task {task_id} for workspace {workspace_id}")

    return ExecuteResponse(
        task_id=task_id,
        status="running",
        feature_id=feature_id,
        message=f"Started {feature.name}",
    )


async def _create_and_start_task(
    workspace_id: str,
    feature: WorkspaceFeature,
    params: dict[str, Any],
    background_tasks: BackgroundTasks,
    user_id: str,
) -> str:
    """Create task and start execution based on feature type.

    Args:
        workspace_id: The workspace ID
        feature: Feature configuration
        params: Execution parameters
        background_tasks: FastAPI background tasks
        user_id: The user ID who initiated the task

    Returns:
        Task ID for status polling
    """
    import uuid

    # For thesis features, use thesis task system
    if feature.agent in ("thesis_writer", "librarian", "figure_planner"):
        from src.thesis.task_storage import create_thesis_task
        from src.thesis.workflow.runner import run_thesis_workflow

        # Get title from params or use default
        paper_title = params.get("title", params.get("paper_title", "未命名论文"))

        # Create thesis task
        task = create_thesis_task(
            workspace_id=workspace_id,
            paper_title=paper_title,
            message=f"Starting {feature.name}...",
        )

        # Build request for workflow
        workflow_request = {
            "workspace_id": workspace_id,
            "paper_title": paper_title,
            "discipline": params.get("discipline", "计算机科学"),
            "abstract_content": params.get("abstract", ""),
            "framework_json": params.get("framework", {}),
            "enable_search": feature.id in ("literature", "outline"),
            "enable_images": feature.id == "figure",
        }

        # Start background workflow
        background_tasks.add_task(
            run_thesis_workflow,
            task.task_id,
            workflow_request,
        )

        return task.task_id

    # For other agents, use generic task system
    from src.task.service import TaskService
    from src.task.store import TaskStore
    from src.academic.cache.redis_client import redis_client

    # Create generic task
    task_id = await TaskService(TaskStore(redis_client, None)).submit_task(
        user_id=user_id,
        task_type=f"feature:{feature.id}",
        payload={
            "workspace_id": workspace_id,
            "feature_id": feature.id,
            "agent": feature.agent,
            **params,
        },
    )

    return task_id

