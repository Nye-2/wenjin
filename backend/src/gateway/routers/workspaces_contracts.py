"""Response contracts for workspace router endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.gateway.validators.workspace import (
    CreateWorkspaceValidator,
    UpdateWorkspaceValidator,
)


class WorkspaceResponse(BaseModel):
    """Workspace response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    type: str
    discipline: str | None
    description: str | None
    config: dict
    created_at: str
    updated_at: str


class WorkspacesListResponse(BaseModel):
    """Workspaces list response."""

    workspaces: list[WorkspaceResponse]


class WorkspaceActivityItemResponse(BaseModel):
    """Workspace activity timeline item."""

    id: str
    kind: str
    workspace_id: str | None = None
    occurred_at: str
    title: str
    summary: str | None = None
    status: str | None = None
    thread_id: str | None = None
    task_id: str | None = None
    artifact_id: str | None = None
    feature_id: str | None = None
    skill: str | None = None
    skill_name: str | None = None
    created_by_skill: str | None = None
    created_by_skill_name: str | None = None
    subagent_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceActivityResponse(BaseModel):
    """Workspace activity feed response."""

    items: list[WorkspaceActivityItemResponse]
    count: int


class WorkspaceSummaryProgressResponse(BaseModel):
    """Workspace task progress summary."""

    completed: int
    in_progress: int
    failed: int
    total: int
    percent: int


class WorkspaceSummaryPhaseResponse(BaseModel):
    """Current workspace phase summary."""

    feature_id: str | None = None
    title: str
    status: str
    description: str | None = None


class WorkspaceSummaryActionResponse(BaseModel):
    """Recommended action for the workspace cockpit."""

    feature_id: str
    title: str
    description: str | None = None
    reason: str | None = None
    status: str
    status_label: str | None = None


class WorkspaceSummaryRiskResponse(BaseModel):
    """Workspace risk prompt."""

    id: str
    title: str
    tone: str


class WorkspaceSummaryRecentActivityResponse(BaseModel):
    """Most recent activity snapshot."""

    title: str
    summary: str | None = None
    kind: str | None = None
    occurred_at: str


class WorkspaceSummaryResponse(BaseModel):
    """Workspace cockpit summary payload."""

    workspace_id: str
    workspace_type: str
    headline: str
    progress: WorkspaceSummaryProgressResponse
    current_phase: WorkspaceSummaryPhaseResponse
    next_step: WorkspaceSummaryActionResponse | None = None
    recommended_actions: list[WorkspaceSummaryActionResponse] = Field(default_factory=list)
    risk_items: list[WorkspaceSummaryRiskResponse] = Field(default_factory=list)
    recent_activity: WorkspaceSummaryRecentActivityResponse | None = None


class ExecutionSessionResponse(BaseModel):
    """Execution session aggregate exposed to frontend runtime surfaces."""

    id: str
    user_id: str
    workspace_id: str
    thread_id: str | None = None
    workspace_type: str
    feature_id: str
    entry_skill_id: str | None = None
    launch_source: str
    launch_message: str | None = None
    status: str
    params: dict[str, Any] = Field(default_factory=dict)
    task_ids: list[str] = Field(default_factory=list)
    primary_task_id: str | None = None
    runtime_snapshot: dict[str, Any] | None = None
    progress: int | None = None
    task_message: str | None = None
    current_step: str | None = None
    result_payload: dict[str, Any] | None = None
    token_usage: dict[str, int] | None = None
    subagents: list[dict[str, Any]] = Field(default_factory=list)
    result_summary: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    next_actions: list[dict[str, Any]] = Field(default_factory=list)
    advisory_code: str | None = None
    last_error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class WorkspaceExecutionSessionsResponse(BaseModel):
    """Execution session list for a workspace."""

    items: list[ExecutionSessionResponse]
    count: int


class WorkspacePrismEnsureResponse(BaseModel):
    """Workspace Prism linkage payload."""

    latex_project_id: str
    url: str
    sync_status: str


CreateWorkspaceRequest = CreateWorkspaceValidator
UpdateWorkspaceRequest = UpdateWorkspaceValidator
