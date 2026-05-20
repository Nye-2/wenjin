"""LaTeX gateway contracts (Pydantic models and type aliases)."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

LatexEngine = Literal["xelatex", "pdflatex"]
RewriteProfile = Literal["balanced", "conservative", "aggressive"]
RewriteRiskLevel = Literal["low", "medium", "high"]

_MAX_REWRITE_CANDIDATES = 3
_REWRITE_CANDIDATE_TIMEOUT_SECONDS = 18

_REWRITE_PROFILE_GUIDANCE: dict[RewriteProfile, str] = {
    "balanced": "在保持原意与结构的前提下做中等强度优化，避免不必要扩写。",
    "conservative": "优先最小改动，尽量保留原句与术语，仅修复明显表达问题。",
    "aggressive": "可进行较大幅度重构以提升清晰度与逻辑性，但不要引入新事实。",
}
_REWRITE_PROFILE_ORDER: tuple[RewriteProfile, ...] = (
    "balanced",
    "conservative",
    "aggressive",
)

_SUPPORTED_ENGINES = frozenset({"xelatex", "pdflatex"})
_FALLBACK_ENGINE = "xelatex"


def get_default_latex_engine() -> LatexEngine:
    """Resolve default LaTeX engine from environment with safe fallback."""
    configured = str(os.getenv("WENJIN_LATEX_DEFAULT_COMPILER", "")).strip().lower()
    if configured and configured in _SUPPORTED_ENGINES:
        return configured  # type: ignore[return-value]
    return _FALLBACK_ENGINE  # type: ignore[return-value]


class LatexProjectResponse(BaseModel):
    """LaTeX project response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    template_id: str | None
    main_file: str
    tags: list[str]
    archived: bool
    trashed: bool
    trashed_at: datetime | None
    file_order: dict[str, list[str]]
    llm_config: dict[str, Any] | None
    workspace_id: str | None = None
    surface_role: str | None = None
    created_at: datetime
    updated_at: datetime


class LatexProjectListResponse(BaseModel):
    """List response for LaTeX projects."""

    projects: list[LatexProjectResponse]


class LatexCreateProjectRequest(BaseModel):
    """Create payload."""

    name: str = Field(min_length=1, max_length=255)
    template_id: str | None = Field(default=None, max_length=50)


class LatexUpdateProjectRequest(BaseModel):
    """Update payload."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    template_id: str | None = Field(default=None, max_length=50)
    main_file: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = None
    archived: bool | None = None
    trashed: bool | None = None
    file_order: dict[str, list[str]] | None = None


class LatexFileItem(BaseModel):
    """File tree item."""

    path: str
    type: Literal["file", "dir"]


class LatexTreeResponse(BaseModel):
    """Tree response."""

    items: list[LatexFileItem]
    file_order: dict[str, list[str]]


class LatexFileContentResponse(BaseModel):
    """Text file payload."""

    content: str


class LatexWriteFileRequest(BaseModel):
    """Write file payload."""

    path: str = Field(min_length=1)
    content: str = ""


class LatexCreateFolderRequest(BaseModel):
    """Create folder payload."""

    path: str = Field(min_length=1)


class LatexRenamePathRequest(BaseModel):
    """Rename payload."""

    from_path: str = Field(alias="from", min_length=1)
    to_path: str = Field(alias="to", min_length=1)


class LatexFileOrderRequest(BaseModel):
    """File order payload."""

    folder: str = ""
    order: list[str]


class LatexCompileRequest(BaseModel):
    """Compile request."""

    main_file: str | None = Field(default=None, max_length=255)
    engine: LatexEngine = Field(default_factory=get_default_latex_engine)


class LatexCompileResponse(BaseModel):
    """Compile response."""

    ok: bool
    status: int
    engine: str
    main_file: str
    pdf_path: str | None
    pdf_endpoint: str | None
    log: str | None
    error: str | None
    history_id: str
    page_count: int | None


class LatexTemplateResponse(BaseModel):
    """Template payload."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    main_file: str
    category: str
    description: str | None
    description_en: str | None
    tags: list[str]
    author: str | None
    featured: bool
    template_path: str | None


class LatexTemplateListResponse(BaseModel):
    """Template list response."""

    templates: list[LatexTemplateResponse]


class LatexUploadResponse(BaseModel):
    """Upload response."""

    ok: bool = True
    files: list[str]
    folders: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


class LatexFeedbackAnchorPayload(BaseModel):
    """Anchor used to re-locate feedback ranges after edits."""

    selected_text: str = ""
    prefix: str = ""
    suffix: str = ""
    heading_title: str = ""
    heading_level: str = ""
    line_hint: int = 1


class LatexFeedbackItemPayload(BaseModel):
    """Stored feedback item in LaTeX project metadata."""

    id: str = Field(min_length=1)
    file_path: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    selected_text: str = ""
    comment: str = Field(min_length=1)
    created_at: datetime | None = None
    anchor: LatexFeedbackAnchorPayload | None = None
    source: Literal["tex", "pdf"] = "tex"
    pdf_anchor: dict[str, Any] | None = None
    last_status: Literal["idle", "pending", "done", "error"] | None = None
    last_error: str | None = None


class LatexFeedbackListResponse(BaseModel):
    """Feedback list response."""

    ok: bool = True
    items: list[LatexFeedbackItemPayload]


class LatexFeedbackSaveRequest(BaseModel):
    """Feedback write request."""

    items: list[LatexFeedbackItemPayload]


class LatexFeedbackRewriteRequest(BaseModel):
    """Rewrite request from one feedback item."""

    file_path: str = Field(min_length=1)
    selected_text: str = Field(min_length=1)
    comment: str = Field(min_length=1)
    selection_start: int | None = Field(default=None, ge=0)
    selection_end: int | None = Field(default=None, ge=0)
    anchor: LatexFeedbackAnchorPayload | None = None
    scope: Literal["selection", "section"] = "section"
    model_id: str | None = None
    file_content: str | None = None
    candidate_count: int | None = Field(
        default=None, ge=1, le=_MAX_REWRITE_CANDIDATES
    )
    apply: bool = False


class LatexFeedbackRewriteResponse(BaseModel):
    """Rewrite preview/apply response."""

    ok: bool = True
    model_id: str
    scope: Literal["selection", "section"]
    file_path: str
    section_title: str
    section_level: str
    resolved_selection_start: int
    resolved_selection_end: int
    target_start: int
    target_end: int
    rewritten_text: str
    changes_summary: str
    proposed_content: str
    updated_anchor: LatexFeedbackAnchorPayload
    applied: bool = False


class LatexDiffStatsPayload(BaseModel):
    """Aggregated diff statistics."""

    chars_added: int = 0
    chars_deleted: int = 0
    tokens_changed: int = 0
    citation_changed: int = 0
    label_changed: int = 0
    math_changed: int = 0


class LatexDiffOpPayload(BaseModel):
    """Single diff operation entry."""

    op: Literal["equal", "insert", "delete", "replace"]
    token_kind: Literal["text", "latex_cmd", "citation", "label", "math", "env"]
    old_text: str = ""
    new_text: str = ""
    old_start: int = Field(ge=0)
    old_end: int = Field(ge=0)
    new_start: int = Field(ge=0)
    new_end: int = Field(ge=0)


class LatexDiffHunkPayload(BaseModel):
    """Diff hunk with contextual operations and local stats."""

    old_start: int = Field(ge=0)
    old_end: int = Field(ge=0)
    new_start: int = Field(ge=0)
    new_end: int = Field(ge=0)
    ops: list[LatexDiffOpPayload]
    stats: LatexDiffStatsPayload
    risk_flags: list[str] = Field(default_factory=list)


class LatexDiffPayload(BaseModel):
    """Full structured diff payload."""

    hunks: list[LatexDiffHunkPayload]
    stats: LatexDiffStatsPayload
    risk_flags: list[str] = Field(default_factory=list)


class LatexFileChangeActionRequest(BaseModel):
    """Address one pending Prism file change."""

    logical_key: str = Field(min_length=1)


class LatexFileChangeApplyRequest(BaseModel):
    """Apply a previewed Prism file change."""

    logical_key: str = Field(min_length=1)
    change_signature: str = Field(min_length=64, max_length=64)


class LatexFileChangeRevertRequest(BaseModel):
    """Revert a previously applied Prism file change."""

    logical_key: str = Field(min_length=1)
    revert_signature: str = Field(min_length=64, max_length=64)


class LatexProtectedSectionRequest(BaseModel):
    """Protect a workspace-owned Prism file or section from direct agent overwrite."""

    path: str = Field(min_length=1)
    section_key: str | None = None
    scope: Literal["file", "section"] = "file"
    reason: str | None = None


class LatexProtectedSectionResponse(BaseModel):
    """Protection write response."""

    ok: bool = True
    protected: bool = True
    path: str
    section_key: str
    scope: Literal["file", "section"]
    reason: str | None = None


class LatexFileChangePreviewResponse(BaseModel):
    """Structured preview for a pending Prism file change."""

    ok: bool = True
    logical_key: str
    path: str
    reason: str
    current_hash: str = Field(min_length=64, max_length=64)
    pending_hash: str = Field(min_length=64, max_length=64)
    change_signature: str = Field(min_length=64, max_length=64)
    diff: LatexDiffPayload


class LatexFileChangeUndoPayload(BaseModel):
    """Signed undo payload stored after applying a Prism file change."""

    logical_key: str
    path: str
    previous_hash: str = Field(min_length=64, max_length=64)
    applied_hash: str = Field(min_length=64, max_length=64)
    revert_signature: str = Field(min_length=64, max_length=64)


class LatexFileChangeApplyResponse(BaseModel):
    """Apply response for a Prism file change."""

    ok: bool = True
    applied: bool = True
    logical_key: str
    path: str
    file_hash: str = Field(min_length=64, max_length=64)
    undo: LatexFileChangeUndoPayload


class LatexFileChangeDiscardResponse(BaseModel):
    """Discard response for a pending Prism file change."""

    ok: bool = True
    discarded: bool = True
    logical_key: str
    path: str


class LatexFileChangeDeferResponse(BaseModel):
    """Defer response for a pending Prism file change."""

    ok: bool = True
    deferred: bool = True
    logical_key: str
    path: str


class LatexFileChangeRevertResponse(BaseModel):
    """Revert response for an applied Prism file change."""

    ok: bool = True
    reverted: bool = True
    logical_key: str
    path: str
    file_hash: str = Field(min_length=64, max_length=64)


class LatexFeedbackRewriteCandidatePayload(BaseModel):
    """Rewrite preview candidate with diff and integrity hashes."""

    candidate_id: str = Field(min_length=1)
    candidate_signature: str = Field(min_length=64, max_length=64)
    profile: RewriteProfile = "balanced"
    risk_level: RewriteRiskLevel = "low"
    model_id: str
    scope: Literal["selection", "section"]
    section_title: str
    section_level: str
    target_start: int = Field(ge=0)
    target_end: int = Field(ge=0)
    rewritten_text: str
    changes_summary: str = ""
    proposed_content: str
    updated_anchor: LatexFeedbackAnchorPayload
    base_file_hash: str = Field(min_length=64, max_length=64)
    base_range_hash: str = Field(min_length=64, max_length=64)
    diff: LatexDiffPayload


class LatexFeedbackRewritePreviewResponse(BaseModel):
    """Rewrite preview response containing one or more candidates."""

    ok: bool = True
    file_path: str
    resolved_selection_start: int = Field(ge=0)
    resolved_selection_end: int = Field(ge=0)
    candidates: list[LatexFeedbackRewriteCandidatePayload]


class LatexFeedbackRewriteApplyRequest(BaseModel):
    """Apply a previously previewed rewrite candidate."""

    file_path: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    candidate_signature: str = Field(min_length=64, max_length=64)
    target_start: int = Field(ge=0)
    target_end: int = Field(ge=0)
    rewritten_text: str
    base_file_hash: str = Field(min_length=64, max_length=64)
    base_range_hash: str = Field(min_length=64, max_length=64)


class LatexFeedbackRewriteUndoPayload(BaseModel):
    """Signed payload that allows one-click rewrite rollback."""

    candidate_id: str = Field(min_length=1)
    revert_start: int = Field(ge=0)
    revert_end: int = Field(ge=0)
    rewritten_text: str
    previous_text: str
    applied_file_hash: str = Field(min_length=64, max_length=64)
    revert_signature: str = Field(min_length=64, max_length=64)


class LatexFeedbackRewriteApplyResponse(BaseModel):
    """Apply rewrite response."""

    ok: bool = True
    applied: bool = True
    file_path: str
    candidate_id: str
    target_start: int = Field(ge=0)
    target_end: int = Field(ge=0)
    rewritten_text: str
    applied_content: str
    updated_anchor: LatexFeedbackAnchorPayload
    file_hash: str = Field(min_length=64, max_length=64)
    undo: LatexFeedbackRewriteUndoPayload


class LatexFeedbackRewriteRevertRequest(BaseModel):
    """Revert a previously applied rewrite candidate."""

    file_path: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    revert_start: int = Field(ge=0)
    revert_end: int = Field(ge=0)
    rewritten_text: str
    previous_text: str
    applied_file_hash: str = Field(min_length=64, max_length=64)
    revert_signature: str = Field(min_length=64, max_length=64)


class LatexFeedbackRewriteRevertResponse(BaseModel):
    """Revert rewrite response."""

    ok: bool = True
    reverted: bool = True
    file_path: str
    candidate_id: str
    revert_start: int = Field(ge=0)
    revert_end: int = Field(ge=0)
    restored_text: str
    reverted_content: str
    updated_anchor: LatexFeedbackAnchorPayload
    file_hash: str = Field(min_length=64, max_length=64)


class LatexFeedbackMapRequest(BaseModel):
    """Map feedback selection back to a TeX range."""

    file_path: str = Field(min_length=1)
    selected_text: str = Field(min_length=1)
    selection_start: int | None = Field(default=None, ge=0)
    selection_end: int | None = Field(default=None, ge=0)
    anchor: LatexFeedbackAnchorPayload | None = None
    history_id: str | None = None
    pdf_anchor: dict[str, Any] | None = None
    file_content: str | None = None
    source: Literal["tex", "pdf"] = "pdf"


class LatexFeedbackMapResponse(BaseModel):
    """Resolved TeX mapping result."""

    ok: bool = True
    file_path: str
    resolved_selection_start: int
    resolved_selection_end: int
    selected_text: str
    updated_anchor: LatexFeedbackAnchorPayload
    section_title: str
    section_level: str
    mapping_method: Literal["synctex", "text_fallback"]
    pdf_anchor: dict[str, Any] | None = None
