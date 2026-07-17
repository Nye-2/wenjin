export type MissionExecutionStatus =
  | "created"
  | "planning"
  | "running"
  | "waiting"
  | "completed"
  | "failed"
  | "cancelled";

export type MissionReviewMode =
  | "review_all"
  | "balanced_default"
  | "auto_draft";

export type MissionRiskLevel = "low" | "medium" | "high";
export type MissionItemPhase =
  | "started"
  | "progress"
  | "completed"
  | "failed"
  | "cancelled";
export type MissionReviewStatus =
  | "pending"
  | "accepted"
  | "rejected"
  | "needs_more_evidence"
  | "committed"
  | "superseded";
export type MissionCommitStatus =
  | "pending"
  | "applying"
  | "committed"
  | "failed"
  | "cancelled";

export interface MissionStageView {
  id: string;
  title: string;
  status: "pending" | "active" | "passed" | "revising" | "waiting";
  summary?: string | null;
}

export interface MissionSubagentView {
  id: string;
  name: string;
  role: string;
  status: "queued" | "working" | "done" | "needs_input" | "failed" | "cancelled";
  summary?: string | null;
}

export interface MissionEvidenceView {
  id: string;
  title: string;
  sourceType: "paper" | "web_page" | "dataset" | "upload" | "artifact";
  sourceLabel?: string | null;
  summary?: string | null;
  citation?: string | null;
  verified: boolean;
}

export interface MissionArtifactView {
  id: string;
  title: string;
  kind: string;
  summary?: string | null;
  previewAvailable: boolean;
  committed: boolean;
}

export type MissionVisualArtifactKind = "figure" | "chart" | "table";

export interface PrismContextRef {
  workspace_id: string;
  prism_project_id: string;
  file_id: string;
  base_revision_ref: string;
  selection_hash: string;
  selection_byte_range: [number, number];
}

export interface MissionVisualReviewMetadata {
  artifactKind: MissionVisualArtifactKind;
  mimeType: string | null;
  figureType: string | null;
  strategy: string | null;
  evidenceLevel: string | null;
  caption: string | null;
  altText: string | null;
  rendererId: string | null;
  reproducibilityStatus: string | null;
  sourceLabels: string[];
}

export interface MissionReviewItemView {
  id: string;
  title: string;
  summary?: string | null;
  targetKind: string;
  riskLevel: MissionRiskLevel;
  status: MissionReviewStatus;
  suggestedSelected: boolean;
  batchAcceptable: boolean;
  requiresExplicitReview: boolean;
  reasonLabel?: string | null;
  preview?: Record<string, unknown> | null;
  previewAvailable: boolean;
  previewUrl?: string | null;
  visual?: MissionVisualReviewMetadata | null;
  commitStatus?: MissionCommitStatus | null;
  commitEligible: boolean;
  commitBlockReason?: string | null;
  commitErrorCode?: string | null;
  committedTargetRef?: string | null;
}

export interface MissionReviewPreviewFile {
  blob: Blob;
  mimeType: string;
}

export interface MissionReviewSummary {
  pending: number;
  needsMoreEvidence: number;
  accepted: number;
  committed: number;
}

export interface MissionCommitSummary {
  pending: number;
  applying: number;
  committed: number;
  failed: number;
}

export interface MissionAttentionInput {
  id: string;
  label: string;
  description?: string | null;
  inputType: "text" | "file" | "confirmation" | "credits";
  required: boolean;
}

export interface MissionAttentionAction {
  id: string;
  label: string;
  actionType:
    | "reply_in_chat"
    | "upload_file"
    | "open_review"
    | "permission_allow_once"
    | "permission_allow_mission"
    | "permission_reject";
  primary: boolean;
}

export interface MissionAttentionRequest {
  requestId: string;
  reason: string;
  title: string;
  summary: string;
  impact: string;
  requiredInputs: MissionAttentionInput[];
  actions: MissionAttentionAction[];
}

export type MissionActivityState =
  | "starting"
  | "working"
  | "collaborating"
  | "retrying"
  | "recovering"
  | "waiting"
  | "reviewing"
  | "completed"
  | "unavailable"
  | "stopped";

export interface MissionActivityView {
  state: MissionActivityState;
  title: string;
  summary?: string | null;
  attempt?: number | null;
  retryAt?: string | null;
}

export interface MissionView {
  missionId: string;
  workspaceId: string;
  threadId?: string | null;
  title: string;
  objective?: string | null;
  executionStatus: MissionExecutionStatus;
  statusLabel: string;
  activity: MissionActivityView;
  attentionRequest: MissionAttentionRequest | null;
  createdAt: string;
  updatedAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  durationSeconds?: number | null;
  activeStage?: MissionStageView | null;
  stages: MissionStageView[];
  requiredStageIds: string[];
  teamSummary?: string | null;
  subagents: MissionSubagentView[];
  evidenceItems: MissionEvidenceView[];
  artifactItems: MissionArtifactView[];
  evidenceNextCursor?: number | null;
  artifactNextCursor?: number | null;
  evidenceCount: number;
  artifactCount: number;
  reviewItems: MissionReviewItemView[];
  reviewSummary: MissionReviewSummary;
  reviewMode: MissionReviewMode;
  reviewPolicy: {
    protectedOutputsRequireConfirmation: boolean;
    draftOutputsMayBeAutomatic: boolean;
  };
  reviewSelectionRevision: string;
  commitSummary: MissionCommitSummary;
  qualityHighlights: string[];
  lastItemSeq: number;
  stateVersion: number;
  isStale?: boolean;
  loadError?: string | null;
}

export interface MissionSummary {
  missionId: string;
  title: string;
  executionStatus: MissionExecutionStatus;
  statusLabel: string;
  updatedAt: string;
  durationSeconds?: number | null;
  activeStage?: string | null;
  pendingReviewCount: number;
  evidenceCount: number;
  artifactCount: number;
}

export interface MissionWorkspaceSummary {
  total: number;
  statusCounts: Record<string, number>;
  pendingReviewCount: number;
  evidenceCount: number;
  artifactCount: number;
  latest: MissionSummary | null;
  active: MissionSummary | null;
}

export interface MissionItem {
  id: string;
  missionId: string;
  seq: number;
  itemType: string;
  phase: MissionItemPhase;
  stageId?: string | null;
  producer?: string | null;
  summary?: string | null;
  createdAt: string;
  detailAvailable?: boolean;
}

export interface MissionPage<T> {
  items: T[];
  nextCursor: string | null;
}

export interface MissionProjectionPage<T> {
  items: T[];
  nextCursor: number | null;
  total: number;
}

export interface MissionReviewDecision {
  reviewItemId: string;
  decision: "accepted" | "rejected" | "needs_more_evidence";
}

export interface MissionEventHint {
  type: "mission.updated";
  missionId: string;
  stateVersion: number;
  lastItemSeq: number;
  cursor: string;
}
