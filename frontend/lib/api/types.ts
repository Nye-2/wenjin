import type { WorkspaceType } from "@/lib/workspace-types";
import type { MissionReviewMode } from "@/lib/api/mission-types";
import type { ReasoningEffort } from "@/lib/reasoning-effort";

export interface Workspace {
  id: string;
  user_id: string;
  name: string;
  type: WorkspaceType;
  discipline?: string;
  description?: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceSettings {
  workspace_id: string;
  default_model: string | null;
  reasoning_effort: ReasoningEffort;
  auto_compact_threshold: number;
  review_mode: MissionReviewMode;
  settings_json: Record<string, unknown>;
  metadata_json: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorkspaceSettingsUpdate {
  default_model?: string | null;
  reasoning_effort?: ReasoningEffort;
  auto_compact_threshold?: number;
  review_mode?: MissionReviewMode;
  metadata_json?: Record<string, unknown>;
}

export interface WorkspacePrismSourceLink {
  id: string;
  workspace_id: string;
  latex_project_id?: string | null;
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
  logical_key?: string | null;
  status: string;
  title: string;
  summary?: string | null;
  source?: {
    type?: string | null;
    mission_id?: string | null;
    task_id?: string | null;
    job_id?: string | null;
  };
  target?: {
    kind?: string | null;
    file_path?: string | null;
    path?: string | null;
    artifact_kind?: string | null;
    asset_id?: string | null;
    sandbox_artifact_id?: string | null;
    room?: string | null;
    item_id?: string | null;
  };
  preview?: {
    mode?: string | null;
    path?: string | null;
    mime_type?: string | null;
    content_hash?: string | null;
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
  kind?: string | null;
  mission_id?: string | null;
  mission_policy_id?: string | null;
  title: string;
  summary?: string | null;
  status: string;
  artifact_count?: number | null;
  duration_seconds?: number | null;
  occurred_at?: string | null;
  created_at?: string | null;
  metadata?: Record<string, unknown>;
}

export interface WorkspacePrismContextSummary {
  decision_count?: number;
  memory_preference_count?: number;
  recent_activity_count?: number;
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
  mission_id?: string | null;
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
  ingest_mission_id?: string | null;
  ingest_mission_commit_id?: string | null;
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
  ingest_mission_id?: string | null;
  ingest_mission_commit_id?: string | null;
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
  messages: ThreadMessage[];
  created_at: string;
  updated_at: string;
}

export interface ThreadSummary {
  id: string;
  workspace_id?: string;
  title?: string | null;
  model: string;
  message_count?: number;
  last_message_preview?: string | null;
  last_message_role?: "user" | "assistant" | "system" | null;
  created_at: string;
  updated_at: string;
}

export interface ThreadRuntimeStatus {
  thread_id: string;
  status: "idle" | "running" | "completed" | "failed";
  subagent_count?: number;
}

export interface TokenUsageCounter {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface WorkspaceActivityItem {
  id: string;
  kind: "mission";
  workspace_id?: string | null;
  occurred_at: string;
  title: string;
  summary?: string | null;
  status?: string | null;
  thread_id?: string | null;
  mission_id?: string | null;
  mission_policy_id?: string | null;
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
    mission_id?: string | null;
    task_type?: string | null;
    status: string;
    progress: number;
    message?: string | null;
    current_step?: string | null;
    mission_policy_id?: string | null;
    thread_id?: string | null;
    metadata?: Record<string, unknown> | null;
    result?: Record<string, unknown> | null;
    error?: string | null;
  };
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
  timestamp?: string;
}

export interface WorkspaceThreadDeletedEvent {
  type: "thread.deleted";
  workspace_id: string;
  thread_id: string;
  timestamp?: string;
}

export interface WorkspaceSubagentUpdatedEvent {
  type: "subagent.updated";
  workspace_id: string;
  subagent: {
    task_id: string;
    thread_id: string;
    mission_id: string;
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
  timestamp?: string;
}

export type WorkspaceEvent =
  | WorkspaceRefreshEvent
  | WorkspaceReadyEvent
  | WorkspaceTaskEvent
  | WorkspaceThreadStatusEvent
  | WorkspaceThreadUpdatedEvent
  | WorkspaceThreadDeletedEvent
  | WorkspaceSubagentUpdatedEvent;

export interface RunRequest {
  message: string;
  workspace_id?: string;
  thread_id?: string;
  model?: string;
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

export interface Model {
  name: string;
  display_name: string;
  category?: string;
  provider: string;
  max_tokens: number;
  generation_api: ModelGenerationApi | null;
  capability_profile_version: string;
  capability_profile: {
    strict_tool_calls: boolean;
    streaming: boolean;
    reasoning_efforts: ReasoningEffort[];
    vision: boolean;
    native_web_search: boolean;
  };
  is_default?: boolean;
}

export type ModelPurpose = "chat" | "writing" | "image" | "all";

export type ModelGenerationApi = "chat_completions";
export type ModelTransportApi = "chat_completions" | "responses";

export interface ModelCapabilityProbeCheck {
  name: string;
  status: "passed" | "failed" | "skipped";
  detail_code?: string | null;
}

export interface ModelTransportObservation {
  transport_api: ModelTransportApi;
  protocol_conformance: boolean;
  detail_code?: string | null;
}

export interface ModelCapabilityProbe {
  probe_version: string;
  model_id: string;
  model_name: string;
  generation_api: ModelGenerationApi | null;
  endpoint_fingerprint: string;
  observed_at: string;
  checks: ModelCapabilityProbeCheck[];
  web_search_api: "responses_web_search" | "none";
  search_receipts: Array<"web_search_call" | "annotations_sources">;
  transport_observations: ModelTransportObservation[];
}

export interface AdminModelCapabilityProfile {
  profile_version: string;
  model_id: string;
  generation_api: ModelGenerationApi | null;
  structured_tool_calls: boolean;
  strict_tool_arguments: boolean;
  streaming: boolean;
  reasoning_efforts: ReasoningEffort[];
  native_web_search: boolean;
  web_search_api: "responses_web_search" | "none";
  search_receipts: Array<"web_search_call" | "annotations_sources">;
  structured_outputs: boolean;
  vision: boolean;
  response_storage_disabled: boolean;
  protocol_conformance: boolean;
  transport_observations: ModelTransportObservation[];
  observed_at: string;
  probe_hash: string;
  endpoint_fingerprint: string;
}

export interface AdminModelCatalogItem {
  id?: string | null;
  model_id: string;
  display_name: string;
  generation_api: ModelGenerationApi | null;
  provider_name: string;
  category: string;
  model_name: string;
  base_url: string;
  api_key_redacted?: string | null;
  enabled: boolean;
  is_default: boolean;
  capability_profile: AdminModelCapabilityProfile;
  capability_probe: ModelCapabilityProbe;
  capability_probe_hash: string;
  capability_observed_at: string;
  max_tokens: number;
  temperature: number;
  timeout_seconds?: number | null;
  max_retries?: number | null;
  trust_level: string;
  pricing_policy_id?: string | null;
  config_version: number;
  health_status: string;
  last_tested_at?: string | null;
  last_test_error?: string | null;
  default_headers: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AdminPricingPolicy {
  id?: string | null;
  policy_key: string;
  policy_kind: string;
  name: string;
  enabled: boolean;
  version: number;
  config: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AdminPricingSimulationRequest {
  policy_kind: string;
  surface?: string;
  global_policy: Record<string, unknown>;
  model_usage_policy?: Record<string, unknown> | null;
  mission_policy?: Record<string, unknown> | null;
  tool_policy?: Record<string, unknown> | null;
  sandbox_policy?: Record<string, unknown> | null;
  prompt_tokens?: number;
  completion_tokens?: number;
}

export interface AdminPricingSimulationResult {
  charge_credits: number;
  raw_cost_cny?: number | null;
  margin_cny?: number | null;
  breakdown: Record<string, unknown>;
}

export interface WorkspacePrismEnsureResponse {
  latex_project_id?: string | null;
  prism_project_id?: string | null;
  url: string;
  sync_status: string;
}

export interface WorkspacePrismFile {
  id: string;
  workspace_id: string;
  document_id: string;
  path: string;
  file_role: string;
  mime_type?: string | null;
  current_version_id?: string | null;
  content_hash?: string | null;
  sort_order: number;
  metadata_json?: Record<string, unknown>;
  deleted_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorkspacePrismFileVersion {
  id: string;
  workspace_id: string;
  file_id: string;
  version_no: number;
  review_item_id?: string | null;
  content_inline?: string | null;
  content_asset_id?: string | null;
  content_hash: string;
  created_by: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorkspacePrismFileContent {
  file: WorkspacePrismFile;
  current_version?: WorkspacePrismFileVersion | null;
}

export interface WorkspacePrismFileWrite {
  file: WorkspacePrismFile;
  version?: WorkspacePrismFileVersion | null;
  changed: boolean;
  skipped_reason?: string | null;
}

export interface WorkspacePrismSurfaceResponse {
  workspace_id: string;
  prism_project_id?: string | null;
  prism_document_id?: string | null;
  prism_files?: WorkspacePrismFile[];
  latex_project_id?: string | null;
  surface_role: string;
  url: string;
  main_file?: string | null;
  compile_status?: string | null;
  has_pending_changes: boolean;
  target_files: string[];
  review_items?: WorkspacePrismReviewItem[];
  source_links?: WorkspacePrismSourceLink[];
  protected_sections?: WorkspacePrismProtectedSection[];
  decisions?: WorkspacePrismDecision[];
  memory_preferences?: WorkspacePrismMemoryPreference[];
  recent_activity?: WorkspacePrismRecentActivity[];
  review_summary?: WorkspacePrismReviewSummary;
  context_summary?: WorkspacePrismContextSummary;
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
  mission_id?: string | null;
  mission_policy_id?: string | null;
  title: string;
  status: string;
  description?: string | null;
}

export interface WorkspaceSummaryAction {
  mission_id: string;
  mission_policy_id?: string | null;
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

export interface CreditTransactionItem {
  id: string;
  user_id?: string;
  user_email?: string;
  user_name?: string | null;
  type: string;
  amount: number;
  balance_after: number;
  description?: string | null;
  mission_policy_id?: string | null;
  mission_id?: string | null;
  operation_key?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface PublicModelPricing {
  model_id: string;
  display_name: string;
  is_default: boolean;
  policy_id: string;
  policy_key: string;
  policy_version: number;
  minimum_credits: number;
}

export interface PublicMissionPricing {
  policy_id: string;
  policy_key: string;
  policy_version: number;
  workspace_type: string | null;
  mission_policy_id: string | null;
  base_fee_credits: number;
  estimate_min_credits: number;
  estimate_max_credits: number;
  max_charge_credits: number;
}

export interface PublicPricingCatalog {
  unit: "credits";
  chat_models: PublicModelPricing[];
  missions: PublicMissionPricing[];
}

export interface ThreadCreditStatus {
  enabled: boolean;
  can_start_thread: boolean;
  overdraft_credits: number;
  billing_unit: "credits";
  pricing: "usage_based";
}

export interface DashboardTokenUsageSection {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  records: number;
  records_with_usage: number;
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
    pricing: PublicPricingCatalog;
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

import type { AgentBlock } from "./blocks";

export interface ThreadBlockEvent {
  type: "block";
  message_id: string;
  block: AgentBlock;
}
