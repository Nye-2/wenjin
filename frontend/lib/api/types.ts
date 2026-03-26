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

export interface WorkspaceCreate {
  name: string;
  type: string;
  discipline?: string;
  description?: string;
  config?: Record<string, unknown>;
}

export interface Paper {
  id: string;
  doi?: string;
  title: string;
  authors: Array<{ name: string; id?: string }>;
  year?: number;
  venue?: string;
  abstract?: string;
  source: string;
  citation_count?: number;
  reference_count?: number;
  file_url?: string | null;
}

export interface PaperExtractionSubmission {
  task_id?: string | null;
  status: string;
  paper_id?: string | null;
  workspace_id?: string | null;
  tier?: number | null;
  message?: string | null;
  progress?: number | null;
  current_step?: string | null;
  error?: string | null;
  reused_existing_task?: boolean;
}

export interface UploadPaperResponse {
  success: boolean;
  paper_id: string;
  filename: string;
  size_bytes: number;
  workspace_id: string;
  file_url?: string | null;
  extraction?: PaperExtractionSubmission | null;
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

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string;
  blocks?: ChatMessageBlock[];
  metadata?: Record<string, unknown>;
}

export type ChatUploadKind = "literature" | "workspace_context" | "transient";

export interface ChatAttachment {
  name: string;
  path: string;
  kind: ChatUploadKind;
  url?: string | null;
  content_type?: string | null;
  size_bytes?: number | null;
  paper_id?: string | null;
  artifact_id?: string | null;
  metadata?: Record<string, unknown>;
}

export interface ChatMessageBlock {
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
  messages: ChatMessage[];
  created_at: string;
  updated_at: string;
}

export interface ThreadSummary {
  id: string;
  workspace_id?: string;
  title?: string | null;
  model: string;
  skill?: string | null;
  message_count?: number;
  last_message_preview?: string | null;
  last_message_role?: "user" | "assistant" | "system" | null;
  created_at: string;
  updated_at: string;
}

export interface ThreadAgentStatus {
  thread_id: string;
  status: "idle" | "running" | "completed" | "failed";
  current_skill?: string | null;
  subagent_count?: number;
}

export interface WorkspaceActivityItem {
  id: string;
  kind: "feature_task" | "chat_thread" | "subagent_task" | "artifact";
  workspace_id?: string | null;
  occurred_at: string;
  title: string;
  summary?: string | null;
  status?: string | null;
  thread_id?: string | null;
  task_id?: string | null;
  artifact_id?: string | null;
  feature_id?: string | null;
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
  thread: ThreadAgentStatus;
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

export interface WorkspaceSubagentUpdatedEvent {
  type: "subagent.updated";
  workspace_id: string;
  subagent: {
    task_id: string;
    thread_id: string;
    status: string;
    subagent_type?: string | null;
    output_preview?: string | null;
    error?: string | null;
  };
  activity?: WorkspaceActivityItem;
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

export type ReasoningEffort = "minimal" | "low" | "medium" | "high";

export interface ChatRequest {
  message: string;
  workspace_id?: string;
  thread_id?: string;
  model?: string;
  skill?: string | null;
  thinking_enabled?: boolean;
  reasoning_effort?: ReasoningEffort;
  stream?: boolean;
  attachments?: ChatAttachment[];
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

export interface WorkspaceFeature {
  id: string;
  name: string;
  description: string;
  icon: string;
  agent: string;
  agentLabel: string;
  taskType?: string;
  handlerKey?: string | null;
  panel?: string | null;
  stages: FeatureStage[];
  color?: string;
}

export interface ExecuteWorkspaceFeatureResponse {
  task_id: string | null;
  status: string;
  feature_id: string;
  message: string;
  warning?: string;
  detail?: Record<string, unknown> | null;
}

export interface TaskStatus {
  task_id: string;
  task_type: string;
  status: string;
  progress: number;
  message?: string;
  result?: Record<string, unknown> | null;
  error?: string | null;
  metadata?: Record<string, unknown> | null;
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

export interface ChatCreditStatus {
  enabled: boolean;
  free_tokens: number;
  tokens_per_credit: number;
  consumed_tokens: number;
  remaining_free_tokens: number;
  can_start_chat: boolean;
  overdraft_credits: number;
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
    chat?: ChatCreditStatus;
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

export interface Literature {
  id: string;
  title: string;
  authors: string[];
  year: number | null;
  citations: number | null;
  venue: string | null;
  quartile: string | null;
  abstract: string | null;
  doi: string | null;
  source: string;
  is_core: boolean;
  created_at: string;
}

export interface LiteratureListResponse {
  items: Literature[];
  total: number;
  core_count: number;
}
