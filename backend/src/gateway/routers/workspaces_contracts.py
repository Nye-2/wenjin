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
    description: str | None
    config: dict[str, Any]
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
    mission_id: str | None = None
    mission_policy_id: str | None = None
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

    mission_id: str | None = None
    mission_policy_id: str | None = None
    title: str
    status: str
    description: str | None = None


class WorkspaceSummaryActionResponse(BaseModel):
    """Recommended action for the workspace cockpit."""

    mission_id: str
    mission_policy_id: str | None = None
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


class WorkspacePrismEnsureResponse(BaseModel):
    """Workspace Prism linkage payload."""

    latex_project_id: str | None = None
    prism_project_id: str | None = None
    url: str
    sync_status: str


class WorkspacePrismFileResponse(BaseModel):
    """Prism file metadata shown in the file workspace."""

    id: str
    workspace_id: str
    document_id: str
    path: str
    file_role: str
    mime_type: str | None = None
    current_version_id: str | None = None
    content_hash: str | None = None
    sort_order: int = 0
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    deleted_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class WorkspacePrismFileVersionResponse(BaseModel):
    """Current Prism file version content."""

    model_config = ConfigDict(extra="forbid")

    id: str
    workspace_id: str
    file_id: str
    version_no: int
    mission_review_item_id: str | None = None
    mission_commit_id: str | None = None
    content_inline: str | None = None
    content_asset_id: str | None = None
    content_hash: str
    created_by: str
    created_at: str | None = None
    updated_at: str | None = None


class WorkspacePrismFileContentResponse(BaseModel):
    """Prism file plus current version."""

    file: WorkspacePrismFileResponse
    current_version: WorkspacePrismFileVersionResponse | None = None


class WorkspacePrismFileUpsertRequest(BaseModel):
    """Create or replace a workspace Prism file path."""

    path: str = Field(min_length=1, max_length=1024)
    content_inline: str = ""
    file_role: str = Field(default="manual", max_length=50)
    mime_type: str | None = Field(default=None, max_length=100)


class WorkspacePrismFileSaveRequest(BaseModel):
    """Autosave text content for an existing Prism file."""

    content_inline: str
    expected_current_hash: str | None = Field(default=None, max_length=128)


class WorkspacePrismFileWriteResponse(BaseModel):
    """Prism file write result."""

    file: WorkspacePrismFileResponse
    version: WorkspacePrismFileVersionResponse | None = None
    changed: bool = False
    skipped_reason: str | None = None


class WorkspacePrismSurfaceResponse(BaseModel):
    """Workspace-owned Prism surface projection."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "workspace_id": "ws-1",
                "latex_project_id": "latex-1",
                "surface_role": "primary_manuscript",
                "url": "/workspaces/ws-1/prism",
                "main_file": "main.tex",
                "compile_status": None,
                "has_pending_changes": True,
                "target_files": ["main.tex", "sections/introduction.tex"],
                "review_items": [],
                "source_links": [],
                "protected_sections": [],
                "decisions": [],
                "memory_preferences": [],
                "recent_activity": [],
                "review_summary": {
                    "pending_count": 1,
                    "applied_count": 0,
                    "source_link_count": 0,
                    "protected_section_count": 0,
                },
                "context_summary": {
                    "decision_count": 0,
                    "memory_preference_count": 0,
                    "recent_activity_count": 0,
                },
            }
        }
    )

    workspace_id: str
    prism_project_id: str | None = None
    prism_document_id: str | None = None
    prism_files: list[WorkspacePrismFileResponse] = Field(default_factory=list)
    latex_project_id: str | None = None
    surface_role: str
    url: str
    main_file: str | None = None
    compile_status: str | None = None
    has_pending_changes: bool = False
    target_files: list[str] = Field(default_factory=list)
    review_items: list[dict[str, Any]] = Field(default_factory=list)
    source_links: list[dict[str, Any]] = Field(default_factory=list)
    protected_sections: list[dict[str, Any]] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    memory_preferences: list[dict[str, Any]] = Field(default_factory=list)
    recent_activity: list[dict[str, Any]] = Field(default_factory=list)
    review_summary: dict[str, int] = Field(default_factory=dict)
    context_summary: dict[str, int] = Field(default_factory=dict)


CreateWorkspaceRequest = CreateWorkspaceValidator
UpdateWorkspaceRequest = UpdateWorkspaceValidator
