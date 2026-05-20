export interface Workspace {
  id: string;
  user_id: string;
  name: string;
  type: "sci" | "thesis" | "proposal" | "software_copyright" | "patent";
  discipline?: string;
  description?: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface LatexProject {
  id: string;
  user_id: string;
  name: string;
  template_id?: string | null;
  main_file: string;
  tags: string[];
  archived: boolean;
  trashed: boolean;
  trashed_at?: string | null;
  file_order: Record<string, string[]>;
  llm_config?: Record<string, unknown> | null;
  workspace_id?: string | null;
  surface_role?: string | null;
  created_at: string;
  updated_at: string;
}

export interface LatexProjectCreate {
  name: string;
  template_id?: string | null;
}

export interface LatexFileItem {
  path: string;
  type: "file" | "dir";
}

export interface LatexTemplate {
  id: string;
  label: string;
  main_file: string;
  category: string;
  description?: string | null;
  description_en?: string | null;
  tags: string[];
  author?: string | null;
  featured: boolean;
  template_path?: string | null;
}

export type LatexCompileEngine =
  | "xelatex"
  | "pdflatex";

export interface LatexCompileResult {
  ok: boolean;
  status: number;
  engine: LatexCompileEngine;
  main_file: string;
  pdf_path?: string | null;
  pdf_endpoint?: string | null;
  log?: string | null;
  error?: string | null;
  history_id: string;
  page_count?: number | null;
}

export interface LatexFileChange {
  id?: string | null;
  logical_key: string;
  path: string;
  reason: string;
  status?: string | null;
  title?: string | null;
  source_type?: string | null;
  source_execution_id?: string | null;
  source_task_id?: string | null;
  target_kind?: string | null;
  applied_at?: string | null;
  pending_content?: string | null;
  current_hash?: string | null;
  pending_hash?: string | null;
}

export interface LatexAppliedFileChange {
  id?: string | null;
  logical_key: string;
  path: string;
  reason?: string | null;
  status?: string | null;
  title?: string | null;
  source_type?: string | null;
  source_execution_id?: string | null;
  source_task_id?: string | null;
  previous_hash: string;
  applied_hash: string;
  revert_signature: string;
  applied_at?: string | null;
}

export interface WorkspacePrismSourceLink {
  id: string;
  workspace_id: string;
  latex_project_id: string;
  review_item_id?: string | null;
  source_type: string;
  source_id: string;
  file_path: string;
  section_key: string;
  quote?: string | null;
  citation_key?: string | null;
  usage: string;
  created_at?: string | null;
}

export interface WorkspacePrismProtectedSection {
  id: string;
  workspace_id: string;
  latex_project_id: string;
  file_path: string;
  section_key: string;
  scope: string;
  reason?: string | null;
  source: string;
  updated_at?: string | null;
}

export interface WorkspacePrismReviewSummary {
  pending_count?: number;
  applied_count?: number;
  source_link_count?: number;
  protected_section_count?: number;
}

export interface WorkspacePrismReviewItem {
  id: string;
  kind: string;
  logical_key: string;
  status: string;
  title: string;
  summary?: string | null;
  source?: {
    type?: string | null;
    execution_id?: string | null;
    task_id?: string | null;
  };
  target?: {
    kind?: string | null;
    file_path?: string | null;
    room?: string | null;
    item_id?: string | null;
  };
  preview?: {
    mode?: string | null;
    pending_hash?: string | null;
    current_hash?: string | null;
    applied_hash?: string | null;
    revert_signature?: string | null;
  };
  actions?: Array<{
    action: string;
    label: string;
  }>;
  created_at?: string | null;
  updated_at?: string | null;
  applied_at?: string | null;
}

export interface WorkspacePrismDecision {
  id: string;
  workspace_id: string;
  key: string;
  value: string;
  confidence?: number | null;
  extracted_by?: string | null;
  created_at?: string | null;
}

export interface WorkspacePrismMemoryPreference {
  id: string;
  workspace_id: string;
  category: string;
  content: string;
  confidence?: number | null;
  reference_count?: number | null;
  last_referenced_at?: string | null;
  created_at?: string | null;
}

export interface WorkspacePrismRecentActivity {
  id: string;
  workspace_id: string;
  execution_id: string;
  capability_id: string;
  title: string;
  summary?: string | null;
  status: string;
  artifact_count?: number | null;
  duration_seconds?: number | null;
  created_at?: string | null;
}

export interface WorkspacePrismContextSummary {
  decision_count?: number;
  memory_preference_count?: number;
  recent_activity_count?: number;
}

export interface LatexFeedbackAnchor {
  selected_text: string;
  prefix: string;
  suffix: string;
  heading_title: string;
  heading_level: string;
  line_hint: number;
}

export interface LatexPdfAnchorRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface LatexPdfAnchor {
  page: number;
  text: string;
  rects: LatexPdfAnchorRect[];
}

export interface LatexFeedbackItem {
  id: string;
  file_path: string;
  start: number;
  end: number;
  selected_text: string;
  comment: string;
  created_at?: string | null;
  anchor?: LatexFeedbackAnchor | null;
  source?: "tex" | "pdf";
  pdf_anchor?: LatexPdfAnchor | null;
  last_status?: "idle" | "pending" | "done" | "error" | null;
  last_error?: string | null;
}

export interface LatexDiffStats {
  chars_added: number;
  chars_deleted: number;
  tokens_changed: number;
  citation_changed: number;
  label_changed: number;
  math_changed: number;
}

export interface LatexDiffOp {
  op: "equal" | "insert" | "delete" | "replace";
  token_kind: "text" | "latex_cmd" | "citation" | "label" | "math" | "env";
  old_text: string;
  new_text: string;
  old_start: number;
  old_end: number;
  new_start: number;
  new_end: number;
}

export interface LatexDiffHunk {
  old_start: number;
  old_end: number;
  new_start: number;
  new_end: number;
  ops: LatexDiffOp[];
  stats: LatexDiffStats;
  risk_flags: string[];
}

export interface LatexRewriteDiffPayload {
  hunks: LatexDiffHunk[];
  stats: LatexDiffStats;
  risk_flags: string[];
}

export interface LatexFileChangePreviewResponse {
  ok: boolean;
  logical_key: string;
  path: string;
  reason: string;
  current_hash: string;
  pending_hash: string;
  change_signature: string;
  diff: LatexRewriteDiffPayload;
}

export interface LatexFileChangeUndoPayload {
  logical_key: string;
  path: string;
  previous_hash: string;
  applied_hash: string;
  revert_signature: string;
}

export interface LatexFileChangeApplyResponse {
  ok: boolean;
  applied: boolean;
  logical_key: string;
  path: string;
  file_hash: string;
  undo: LatexFileChangeUndoPayload;
}

export interface LatexFileChangeDiscardResponse {
  ok: boolean;
  discarded: boolean;
  logical_key: string;
  path: string;
}

export interface LatexFileChangeDeferResponse {
  ok: boolean;
  deferred: boolean;
  logical_key: string;
  path: string;
}

export interface LatexFileChangeRevertResponse {
  ok: boolean;
  reverted: boolean;
  logical_key: string;
  path: string;
  file_hash: string;
}

export interface LatexFeedbackRewriteCandidate {
  candidate_id: string;
  candidate_signature: string;
  profile: "balanced" | "conservative" | "aggressive";
  risk_level: "low" | "medium" | "high";
  model_id: string;
  scope: "selection" | "section";
  section_title: string;
  section_level: string;
  target_start: number;
  target_end: number;
  rewritten_text: string;
  changes_summary: string;
  proposed_content: string;
  updated_anchor: LatexFeedbackAnchor;
  base_file_hash: string;
  base_range_hash: string;
  diff: LatexRewriteDiffPayload;
}

export interface LatexFeedbackRewritePreviewResponse {
  ok: boolean;
  file_path: string;
  resolved_selection_start: number;
  resolved_selection_end: number;
  candidates: LatexFeedbackRewriteCandidate[];
}

export interface LatexFeedbackRewriteApplyResponse {
  ok: boolean;
  applied: boolean;
  file_path: string;
  candidate_id: string;
  target_start: number;
  target_end: number;
  rewritten_text: string;
  applied_content: string;
  updated_anchor: LatexFeedbackAnchor;
  file_hash: string;
  undo: LatexFeedbackRewriteUndoPayload;
}

export interface LatexFeedbackRewriteUndoPayload {
  candidate_id: string;
  revert_start: number;
  revert_end: number;
  rewritten_text: string;
  previous_text: string;
  applied_file_hash: string;
  revert_signature: string;
}

export interface LatexFeedbackRewriteRevertResponse {
  ok: boolean;
  reverted: boolean;
  file_path: string;
  candidate_id: string;
  revert_start: number;
  revert_end: number;
  restored_text: string;
  reverted_content: string;
  updated_anchor: LatexFeedbackAnchor;
  file_hash: string;
}

export interface LatexFeedbackMapResponse {
  ok: boolean;
  file_path: string;
  resolved_selection_start: number;
  resolved_selection_end: number;
  selected_text: string;
  updated_anchor: LatexFeedbackAnchor;
  section_title: string;
  section_level: string;
  mapping_method: "synctex" | "text_fallback";
  pdf_anchor?: LatexPdfAnchor | null;
}

export interface WorkspaceCreate {
  name: string;
  type: string;
  discipline?: string;
  description?: string;
  config?: Record<string, unknown>;
}

export interface WorkspaceTemplate {
  id: string;
  name: string;
  category: string;
  sourceType: string;
  structure: Record<string, unknown> | null;
  formatSpec: Record<string, unknown> | null;
  contentGuidelines: Record<string, unknown> | null;
  isActive: boolean;
  isBuiltin: boolean;
}

export interface ReferenceAsset {
  id: string;
  workspace_id: string;
  reference_id: string;
  source_asset_id?: string | null;
  asset_type: "pdf" | "markdown" | "manifest" | string;
  file_path?: string | null;
  virtual_path?: string | null;
  public_url?: string | null;
  content_type?: string | null;
  file_size?: number | null;
  file_hash?: string | null;
  page_count?: number | null;
  language?: string | null;
  preprocess_status?: string | null;
  preprocess_task_id?: string | null;
  preprocess_error?: string | null;
  manifest_path?: string | null;
  markdown_paths?: string[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ReferenceExternalId {
  id: string;
  workspace_id: string;
  reference_id: string;
  source: string;
  external_id: string;
  url?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ReferenceUsageEvent {
  id: string;
  workspace_id: string;
  reference_id: string;
  outline_node_id?: string | null;
  text_unit_id?: string | null;
  execution_id?: string | null;
  task_id?: string | null;
  artifact_id?: string | null;
  latex_project_id?: string | null;
  target_section?: string | null;
  claim_text?: string | null;
  generated_text?: string | null;
  citation_key?: string | null;
  usage_type: string;
  accepted_status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ReferencePreprocessSummary {
  status: string;
  status_counts: Record<string, number>;
  asset_count: number;
  markdown_paths: string[];
  manifest_paths: string[];
  task_ids: string[];
  errors: string[];
}

export interface ReferenceSourceHistoryItem {
  source_type?: string | null;
  source_label?: string | null;
  source_run_id?: string | null;
  source_artifact_id?: string | null;
  external_id?: string | null;
  url?: string | null;
  verified_at?: string | null;
  created_at?: string | null;
}

export interface ReferenceUsageSummary {
  recent_count: number;
  status_counts: Record<string, number>;
  last_used_at?: string | null;
}

export interface WorkspaceReference {
  id: string;
  workspace_id: string;
  title: string;
  normalized_title?: string | null;
  authors: string[];
  year?: number | null;
  venue?: string | null;
  publication_type?: string | null;
  doi?: string | null;
  url?: string | null;
  abstract?: string | null;
  citation_count?: number | null;
  source_type: string;
  source_label?: string | null;
  source_run_id?: string | null;
  source_artifact_id?: string | null;
  verified_at?: string | null;
  library_status: string;
  evidence_level: string;
  fulltext_status: string;
  citation_key?: string | null;
  bibtex_entry_type?: string | null;
  bibtex_fields?: Record<string, unknown>;
  read_status?: string | null;
  tags?: string[];
  notes?: string | null;
  is_deleted?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  assets?: ReferenceAsset[];
}

export interface ReferenceDetailResponse {
  reference: WorkspaceReference;
  assets: ReferenceAsset[];
  external_ids: ReferenceExternalId[];
  source_history: ReferenceSourceHistoryItem[];
  preprocess: ReferencePreprocessSummary;
  usage_events: ReferenceUsageEvent[];
  usage_summary: ReferenceUsageSummary;
}

export interface ReferencePreprocessSubmission {
  task_id?: string | null;
  status: string;
  provider?: string | null;
  file_type?: string | null;
  message?: string | null;
  progress?: number | null;
  current_step?: string | null;
  error?: string | null;
  manifest_path?: string | null;
  markdown_paths?: string[];
  markdown_urls?: string[];
}

export interface UploadReferenceResponse {
  success: boolean;
  reference: WorkspaceReference;
  asset: ReferenceAsset;
  filename: string;
  size_bytes: number;
  workspace_id: string;
  preprocess?: ReferencePreprocessSubmission | null;
}

export interface Artifact {
  id: string;
  workspace_id: string;
  type: string;
  title?: string;
  content: Record<string, unknown>;
  created_by_skill?: string;
  parent_artifact_id?: string;
  version: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ThreadMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string;
  blocks?: ThreadMessageBlock[];
  metadata?: Record<string, unknown>;
}

export type ThreadUploadKind = "literature" | "workspace_context" | "transient";

export interface ThreadAttachment {
  name: string;
  path: string;
  kind: ThreadUploadKind;
  url?: string | null;
  content_type?: string | null;
  size_bytes?: number | null;
  reference_id?: string | null;
  artifact_id?: string | null;
  metadata?: Record<string, unknown>;
}

export interface ThreadMessageBlock {
  type: string;
  title?: string | null;
  data?: Record<string, unknown>;
}

export interface Thread {
  id: string;
  workspace_id?: string;
  title?: string | null;
  model: string;
  skill?: string | null;
  skill_name?: string | null;
  messages: ThreadMessage[];
  created_at: string;
  updated_at: string;
}

export interface ThreadSummary {
  id: string;
  workspace_id?: string;
  title?: string | null;
  model: string;
  skill?: string | null;
  skill_name?: string | null;
  message_count?: number;
  last_message_preview?: string | null;
  last_message_role?: "user" | "assistant" | "system" | null;
  created_at: string;
  updated_at: string;
}

export interface ThreadRuntimeStatus {
  thread_id: string;
  status: "idle" | "running" | "completed" | "failed";
  current_skill?: string | null;
  current_skill_name?: string | null;
  subagent_count?: number;
}

export interface TokenUsageCounter {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface WorkspaceActivityItem {
  id: string;
  kind: "feature_task" | "thread" | "subagent_task" | "artifact";
  workspace_id?: string | null;
  occurred_at: string;
  title: string;
  summary?: string | null;
  status?: string | null;
  thread_id?: string | null;
  task_id?: string | null;
  artifact_id?: string | null;
  feature_id?: string | null;
  skill?: string | null;
  skill_name?: string | null;
  created_by_skill?: string | null;
  created_by_skill_name?: string | null;
  subagent_type?: string | null;
  metadata?: Record<string, unknown>;
}

export interface WorkspaceRefreshEvent {
  type: "workspace.refresh";
  workspace_id: string;
  refresh_targets?: string[];
  timestamp?: string;
}

export interface WorkspaceReadyEvent {
  type: "workspace.ready";
  workspace_id: string;
  message?: string;
  timestamp?: string;
}

export interface WorkspaceTaskEvent {
  type: "task.updated";
  workspace_id: string;
  task: {
    task_id: string;
    execution_id?: string | null;
    task_type?: string | null;
    status: string;
    progress: number;
    message?: string | null;
    current_step?: string | null;
    feature_id?: string | null;
    thread_id?: string | null;
    metadata?: Record<string, unknown> | null;
    result?: Record<string, unknown> | null;
    error?: string | null;
  };
  activity?: WorkspaceActivityItem;
  timestamp?: string;
}

export interface WorkspaceThreadStatusEvent {
  type: "thread.status";
  workspace_id: string;
  thread: ThreadRuntimeStatus;
  timestamp?: string;
}

export interface WorkspaceThreadUpdatedEvent {
  type: "thread.updated";
  workspace_id: string;
  thread: ThreadSummary;
  activity?: WorkspaceActivityItem;
  timestamp?: string;
}

export interface WorkspaceThreadDeletedEvent {
  type: "thread.deleted";
  workspace_id: string;
  thread_id: string;
  activity_id?: string;
  timestamp?: string;
}

export interface ComputeSession {
  id: string;
  execution_id: string;
  workspace_id: string;
  user_id: string;
  sandbox_session_id?: string | null;
  active_view: string;
  ui_state: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ComputeSessionListResponse {
  items: ComputeSession[];
  count: number;
}

export interface ComputeFileProjection {
  id: string;
  kind: string;
  label: string;
  source: string;
  path?: string | null;
  url?: string | null;
  artifact_id?: string | null;
  metadata: Record<string, unknown>;
}

export interface ComputeLogProjection {
  id: string;
  source: string;
  level: "info" | "success" | "warning" | "error" | string;
  title: string;
  message: string;
  timestamp?: string | null;
  truncated?: boolean;
  metadata: Record<string, unknown>;
}

export interface ComputeReviewGateItem {
  id: string;
  kind: string;
  label: string;
  required: boolean;
  payload: Record<string, unknown>;
}

export interface ComputeReviewGateProjection {
  status: "clear" | "awaiting_user" | "advisory" | "failed" | string;
  required: boolean;
  policy?: string | null;
  next_actions: Array<Record<string, unknown>>;
  items: ComputeReviewGateItem[];
  advisory_code?: string | null;
}

export interface ComputeSandboxProjection {
  session_id?: string | null;
  status: "bound" | "derived" | "required" | "unbound" | string;
  required?: boolean;
  files: ComputeFileProjection[];
  logs: ComputeLogProjection[];
  file_count: number;
  log_count: number;
}

export interface ComputeRuntimeProfileProjection {
  workspace_type?: string | null;
  feature_id?: string | null;
  runtime_mode?: "chat_only" | "deterministic" | "compute_workflow" | "compute_agentic" | string;
  requires_compute?: boolean;
  requires_sandbox?: boolean;
  allowed_subagents?: string[];
  max_subagents?: number;
  agent_harness_provider?: string | null;
  output_contract?: string;
  review_gate?: string | null;
}

export interface ComputePrismCompileProjection {
  status?: string | null;
  pdf_path?: string | null;
  pdf_url?: string | null;
  pdf_endpoint?: string | null;
  page_count?: number | null;
  error?: string | null;
}

export interface ComputePrismItemProjection {
  id: string;
  source: string;
  status: "ready" | "pending_changes" | "compile_failed" | string;
  latex_project_id: string;
  url: string;
  main_file: string;
  section_file?: string | null;
  target_files: string[];
  section_map: Record<string, string>;
  file_changes: Array<Record<string, unknown>>;
  applied_file_changes: Array<Record<string, unknown>>;
  compile: ComputePrismCompileProjection;
}

export interface ComputePrismProjection {
  status: "ready" | "pending_changes" | "compile_failed" | "unbound" | string;
  project_id?: string | null;
  url?: string | null;
  main_file?: string | null;
  target_files: string[];
  file_changes: Array<Record<string, unknown>>;
  applied_file_changes: Array<Record<string, unknown>>;
  compile: ComputePrismCompileProjection;
  items: WorkspacePrismReviewItem[];
}

export interface ComputeProjection {
  compute_session: ComputeSession;
  execution: ExecutionRecord;
  primary_task?: Record<string, unknown> | null;
  tasks: Array<Record<string, unknown>>;
  runtime_blocks: Array<Record<string, unknown>>;
  subagents: Array<Record<string, unknown>>;
  artifacts: Record<string, unknown>;
  runtime_profile: ComputeRuntimeProfileProjection;
  sandbox: ComputeSandboxProjection;
  prism: ComputePrismProjection;
  files: ComputeFileProjection[];
  logs: ComputeLogProjection[];
  review_gate: ComputeReviewGateProjection;
}

export interface WorkspaceExecutionUpdatedEvent {
  type: "execution.updated" | "execution.completed" | "execution.failed";
  workspace_id: string;
  execution_id: string;
  event_type: string;
  status?: string | null;
  timestamp?: string;
}

export interface WorkspaceSubagentUpdatedEvent {
  type: "subagent.updated";
  workspace_id: string;
  subagent: {
    task_id: string;
    thread_id: string;
    execution_id: string;
    status: string;
    subagent_type?: string | null;
    workflow_phase?: string | null;
    workflow_phase_index?: string | number | null;
    workflow_task_index?: string | number | null;
    workflow_strategy?: string | null;
    output_preview?: string | null;
    output?: string | null;
    error?: string | null;
    token_usage?: TokenUsageCounter | null;
    model_name?: string | null;
  };
  activity?: WorkspaceActivityItem;
  timestamp?: string;
}

export interface WorkspaceComputeSessionEvent {
  type: "compute.created" | "compute.updated";
  workspace_id: string;
  compute_session: ComputeSession;
  timestamp?: string;
}

export type WorkspaceEvent =
  | WorkspaceRefreshEvent
  | WorkspaceReadyEvent
  | WorkspaceTaskEvent
  | WorkspaceThreadStatusEvent
  | WorkspaceThreadUpdatedEvent
  | WorkspaceThreadDeletedEvent
  | WorkspaceExecutionUpdatedEvent
  | WorkspaceSubagentUpdatedEvent
  | WorkspaceComputeSessionEvent;

export type ReasoningEffort = "minimal" | "low" | "medium" | "high";

export interface RunRequest {
  message: string;
  workspace_id?: string;
  thread_id?: string;
  model?: string;
  skill?: string | null;
  thinking_enabled?: boolean;
  reasoning_effort?: ReasoningEffort;
  attachments?: ThreadAttachment[];
  metadata?: Record<string, unknown>;
  on_disconnect?: RunDisconnectMode;
  multitask_strategy?: RunMultitaskStrategy;
}

export type RunDisconnectMode = "cancel" | "continue";
export type RunMultitaskStrategy = "reject" | "interrupt" | "rollback";
export type RunCancelAction = "interrupt" | "rollback";

export interface RunResponse {
  run_id: string;
  thread_id: string;
  assistant_id?: string | null;
  status: "pending" | "running" | "success" | "error" | "interrupted" | string;
  metadata?: Record<string, unknown>;
  kwargs?: Record<string, unknown>;
  multitask_strategy?: string;
  error?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface RunWaitResponse {
  run_id: string;
  thread_id: string;
  status: "pending" | "running" | "success" | "error" | "interrupted" | string;
  error?: string | null;
  values?: Record<string, unknown>;
}

export interface PlatformThreadSummary {
  thread_id: string;
  status: "idle" | "busy" | "interrupted" | "error" | string;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
  values: Record<string, unknown>;
  interrupts: Record<string, unknown>;
}

export interface PlatformThreadState {
  values: Record<string, unknown>;
  next: string[];
  metadata: Record<string, unknown>;
  checkpoint: Record<string, unknown>;
  checkpoint_id?: string | null;
  parent_checkpoint_id?: string | null;
  created_at?: string | null;
  tasks: Array<Record<string, unknown>>;
}

export interface PlatformThreadHistoryEntry {
  checkpoint_id: string;
  parent_checkpoint_id?: string | null;
  metadata: Record<string, unknown>;
  values: Record<string, unknown>;
  created_at?: string | null;
  next: string[];
}

export interface Model {
  name: string;
  display_name: string;
  category?: string;
  provider: string;
  max_tokens: number;
  supports_tools?: boolean;
  supports_thinking: boolean;
  supports_reasoning_effort: boolean;
  supports_vision: boolean;
  is_default?: boolean;
}

export type ModelPurpose = "chat" | "writing" | "image" | "all";

export interface FeatureStage {
  id: string;
  label: string;
}

export interface WorkspaceCapability {
  id: string;
  name: string;
  description: string;
  icon: string;
  stages: FeatureStage[];
  color?: string;
  followUpPrompt?: string | null;
  defaultSkillId?: string | null;
}

export interface WorkspacePrismEnsureResponse {
  latex_project_id: string;
  url: string;
  sync_status: string;
}

export interface WorkspacePrismSurfaceResponse {
  workspace_id: string;
  latex_project_id: string;
  surface_role: string;
  url: string;
  main_file?: string | null;
  compile_status?: string | null;
  has_pending_changes: boolean;
  target_files: string[];
  file_changes?: LatexFileChange[];
  applied_file_changes?: LatexAppliedFileChange[];
  review_items?: WorkspacePrismReviewItem[];
  source_links?: WorkspacePrismSourceLink[];
  protected_sections?: WorkspacePrismProtectedSection[];
  decisions?: WorkspacePrismDecision[];
  memory_preferences?: WorkspacePrismMemoryPreference[];
  recent_activity?: WorkspacePrismRecentActivity[];
  review_summary?: WorkspacePrismReviewSummary;
  context_summary?: WorkspacePrismContextSummary;
}

export interface TaskStatus {
  task_id: string;
  execution_id?: string | null;
  task_type: string;
  status: string;
  progress: number;
  message?: string;
  current_step?: string | null;
  result?: Record<string, unknown> | null;
  error?: string | null;
  metadata?: Record<string, unknown> | null;
  workspace_id?: string | null;
  feature_id?: string | null;
  thread_id?: string | null;
  action?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface TaskProgressEvent {
  task_id: string;
  status: string;
  progress: number;
  message?: string | null;
  current_step?: string | null;
  metadata?: Record<string, unknown> | null;
  timestamp?: string;
}

export interface ModuleStatus {
  id: string;
  status: "not_started" | "in_progress" | "completed" | "failed";
  summary: Record<string, unknown>;
}

export interface DashboardData {
  modules: ModuleStatus[];
  recent_artifacts: Array<{
    id: string;
    type: string;
    title: string | null;
    created_at: string;
  }>;
}

export interface WorkspaceSummaryProgress {
  completed: number;
  in_progress: number;
  failed: number;
  total: number;
  percent: number;
}

export interface WorkspaceSummaryPhase {
  feature_id?: string | null;
  title: string;
  status: string;
  description?: string | null;
}

export interface WorkspaceSummaryAction {
  feature_id: string;
  title: string;
  description?: string | null;
  reason?: string | null;
  status: string;
  status_label?: string | null;
}

export interface WorkspaceSummaryRisk {
  id: string;
  title: string;
  tone: "warning" | "danger" | string;
}

export interface WorkspaceSummaryRecentActivity {
  title: string;
  summary?: string | null;
  kind?: string | null;
  occurred_at: string;
}

export interface WorkspaceSummaryData {
  workspace_id: string;
  workspace_type: string;
  headline: string;
  progress: WorkspaceSummaryProgress;
  current_phase: WorkspaceSummaryPhase;
  next_step?: WorkspaceSummaryAction | null;
  recommended_actions: WorkspaceSummaryAction[];
  risk_items: WorkspaceSummaryRisk[];
  recent_activity?: WorkspaceSummaryRecentActivity | null;
}

export interface WorkspaceActivityResponse {
  items: WorkspaceActivityItem[];
  count: number;
}

export interface WorkspaceExecutionsResponse {
  items: ExecutionRecord[];
  count: number;
}

export interface CreditTransactionItem {
  id: string;
  user_id?: string;
  user_email?: string;
  user_name?: string | null;
  type: string;
  amount: number;
  balance_after: number;
  description?: string | null;
  feature_id?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export type CreditCostValue = number | Record<string, number | boolean>;

export interface ThreadCreditStatus {
  enabled: boolean;
  free_tokens: number;
  tokens_per_credit: number;
  consumed_tokens: number;
  remaining_free_tokens: number;
  can_start_thread: boolean;
  overdraft_credits: number;
}

export interface DashboardTokenUsageSection {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  records: number;
  records_with_usage: number;
}

export interface UserDashboardTokenUsage {
  thread: {
    total_tokens: number;
    free_tokens: number;
    billable_tokens: number;
    remaining_free_tokens: number;
  };
  feature_tasks: DashboardTokenUsageSection;
  subagents: DashboardTokenUsageSection;
}

export interface UserDashboardData {
  profile: {
    id: string;
    email: string;
    name: string | null;
    role: "user" | "admin";
    is_active: boolean;
    created_at: string | null;
    last_login: string | null;
  };
  credits: {
    balance: number;
    total_earned: number;
    total_spent: number;
    costs: Record<string, CreditCostValue>;
    thread?: ThreadCreditStatus;
  };
  workspaces: {
    total: number;
    by_type: Record<string, number>;
    created_last_7d: number;
  };
  tasks: {
    total: number;
    success: number;
    running: number;
    failed: number;
    pending: number;
    cancelled: number;
    completion_rate: number;
  };
  token_usage: UserDashboardTokenUsage;
  recent_tasks: Array<{
    id: string;
    task_type: string;
    status: string;
    progress: number;
    message?: string | null;
    created_at: string | null;
    completed_at: string | null;
  }>;
  updated_at: string;
}

export interface AdminUserItem {
  id: string;
  email: string;
  name: string | null;
  role: "user" | "admin";
  is_active: boolean;
  credits: number;
  total_credits_earned: number;
  total_credits_spent: number;
  workspace_count: number;
  task_count: number;
  created_at: string | null;
  last_login: string | null;
}

export interface AdminLogItem {
  id: string;
  admin_id?: string;
  action: string;
  target_type: string;
  target_user_id: string | null;
  details: Record<string, unknown>;
  ip_address?: string | null;
  created_at: string | null;
  admin?: {
    id: string;
    email: string;
    name: string | null;
  };
  target_user?: {
    id: string;
    email: string;
    name: string | null;
  } | null;
}

export interface AdminDashboardData {
  summary: {
    users: {
      total: number;
      active: number;
      admins: number;
    };
    workspaces: {
      total: number;
      by_type: Record<string, number>;
    };
    tasks: {
      total: number;
      running: number;
      failed_last_24h: number;
    };
    artifacts: {
      total: number;
    };
    credits: {
      total_issued: number;
      total_spent: number;
      in_circulation: number;
      manual_deductions: number;
      overdraft_users: number;
      overdraft_credits_total: number;
      total_transactions: number;
    };
    token_usage: {
      thread: {
        total_tokens: number;
        transactions: number;
        users: number;
      };
      feature_tasks: DashboardTokenUsageSection;
      subagents: DashboardTokenUsageSection;
    };
  };
  updated_at: string;
}

export interface ReleaseGateCheck {
  id: string;
  status: "passed" | "failed" | "missing" | "pending";
  description: string;
  fix_hint: string;
  runtime?: {
    command?: string;
    cwd?: string;
    return_code?: number;
    duration_seconds?: number;
    output_tail?: string;
    error?: string | null;
  };
}

export interface ReleaseGateBlock {
  status: "passed" | "failed" | "pending";
  total: number;
  passed: number;
  failed: number;
  missing: number;
  checks: ReleaseGateCheck[];
}

export interface AdminReleaseGateReport {
  status: "passed" | "failed";
  go_no_go: "go" | "no-go";
  core_gate: ReleaseGateBlock;
  extended_gate: ReleaseGateBlock;
  generated_at: string;
  recommendations: string[];
  include_extended?: boolean;
  runner?: {
    project_root?: string;
    backend_root?: string;
    timeout_seconds?: number;
  };
}

export interface McpOAuthConfigInput {
  enabled?: boolean;
  token_url?: string;
  grant_type?: "client_credentials" | "refresh_token";
  client_id?: string | null;
  client_secret?: string | null;
  refresh_token?: string | null;
  scope?: string | null;
  audience?: string | null;
  token_field?: string;
  token_type_field?: string;
  expires_in_field?: string;
  default_token_type?: string;
  refresh_skew_seconds?: number;
  extra_token_params?: Record<string, string>;
}

export interface McpServerConfigInput {
  enabled?: boolean;
  type?: "stdio" | "sse" | "http";
  command?: string | null;
  args?: string[];
  env?: Record<string, string>;
  url?: string | null;
  headers?: Record<string, string>;
  oauth?: McpOAuthConfigInput | null;
  timeout?: number;
  description?: string;
}

export interface McpConfigResponse {
  mcp_servers: Record<string, McpServerConfigInput>;
}

export interface ReferenceListResponse {
  items: WorkspaceReference[];
  total: number;
  core_count: number;
}

export interface ReferenceCountResponse {
  total: number;
  core: number;
  indexed: number;
}

export interface ReferenceImportResponse {
  imported: number;
  created: number;
  items: WorkspaceReference[];
  query?: string | null;
  retrieval?: Record<string, unknown> | null;
  error?: string | null;
}

export interface ReferenceBibtexResponse {
  workspace_id: string;
  scope: string;
  content: string;
  reference_count: number;
  checksum: string;
  latex_project_id?: string;
  synced_file?: string;
}

export interface ReferenceBibtexValidationResponse {
  ok?: boolean;
  valid?: boolean;
  missing_citation_key_reference_ids?: string[];
  duplicate_citation_keys?: string[];
  missing_keys?: string[];
  unused_bib_keys?: string[];
  unverified_keys?: string[];
}

export interface MemoryEntry {
  category: string;
  content: string;
  confidence: number;
  workspace_context?: string | null;
}

export interface MemoryResponse {
  workspace_id?: string | null;
  formatted_context: string;
  items: MemoryEntry[];
}

import type { AgentBlock } from "./blocks";

export interface ThreadBlockEvent {
  type: "block";
  message_id: string;
  block: AgentBlock;
}

// =============================================================================
// Unified Execution Model Types
// =============================================================================

export type KnownExecutionType =
  | "chat_turn"
  | "feature"
  | "subagent"
  | "tool"
  | "advisory"
  | "capability"
  | "latex_compile"
  | "python_plot"
  | "mermaid_diagram"
  | "ai_image";

export type ExecutionType = KnownExecutionType | (string & {});

export type ExecutionStatus =
  | "pending"
  | "running"
  | "cancelling"
  | "completed"
  | "failed_partial"
  | "failed"
  | "cancelled"
  | "awaiting_user_input";

export interface ExecutionRecord {
  id: string;
  user_id: string;
  workspace_id?: string | null;
  thread_id?: string | null;
  execution_type: ExecutionType;
  feature_id?: string | null;
  entry_skill_id?: string | null;
  workspace_type?: string | null;
  display_name?: string | null;
  status: ExecutionStatus;
  params: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  error?: string | null;
  result_summary?: string | null;
  graph_structure?: ExecutionGraphStructure | null;
  node_states: Record<string, ExecutionNodeState>;
  runtime_state?: Record<string, unknown> | null;
  review_items?: WorkspacePrismReviewItem[];
  progress: number;
  message?: string | null;
  artifact_ids: string[];
  next_actions: Record<string, unknown>[];
  advisory_code?: string | null;
  last_error?: string | null;
  parent_execution_id?: string | null;
  child_execution_ids: string[];
  dispatch_mode?: string | null;
  worker_task_id?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at: string;
}

export interface ExecutionGraphStructure {
  nodes: ExecutionGraphNode[];
  edges: ExecutionGraphEdge[];
}

export interface ExecutionGraphNode {
  id: string;
  type: string;
  label?: string;
  phase?: string;
  task?: string;
  subagent_type?: string;
  metadata?: Record<string, unknown>;
}

export interface ExecutionGraphEdge {
  from: string;
  to: string;
  label?: string;
}

export interface ExecutionNodeState {
  status?: string;
  output_preview?: string | null;
  token_usage?: Record<string, number> | null;
  thinking?: string | null;
  tool_calls?: Record<string, unknown>[] | null;
  started_at?: string | null;
  completed_at?: string | null;
  input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
}

export interface ExecutionNodeRecord {
  id: string;
  execution_id: string;
  parent_node_id?: string | null;
  node_id: string;
  node_type: string;
  label?: string | null;
  status: string;
  input_data?: Record<string, unknown> | null;
  output_data?: Record<string, unknown> | null;
  thinking?: string | null;
  tool_calls?: Record<string, unknown>[] | null;
  token_usage?: Record<string, unknown> | null;
  started_at?: string | null;
  completed_at?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

// Execution stream events (SSE)
export type ExecutionStreamEventType =
  | "execution.metadata"
  | "execution.graph_structure"
  | "execution.node"
  | "execution.node.delta"
  | "execution.status"
  | "execution.completed"
  | "execution.error"
  | "execution.end";

export interface ExecutionStreamEvent {
  execution_id: string;
  type: ExecutionStreamEventType;
  timestamp: string;
  payload: Record<string, unknown>;
}
