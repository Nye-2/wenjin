import type {
  ExecutionNodeState,
  ExecutionRecord,
  TokenUsageCounter,
  WorkspaceFeature,
} from "@/lib/api";
import { ACTIVE_EXECUTION_STATUSES } from "@/lib/execution-status";

export interface ExecutionTaskStage {
  id: string;
  label: string;
  status: "completed" | "running" | "pending";
}

export interface ExecutionCurrentTask {
  id: string;
  featureId: string;
  status: "running" | "completed" | "cancelled" | "failed";
  agent: string;
  agentLabel: string;
  thinking: string;
  stages: ExecutionTaskStage[];
  currentStageIndex: number;
  startedAt: string;
  completedAt?: string;
}

export interface ExecutionPanelSubagent {
  id: string;
  threadId: string;
  subagentType: string | null;
  workflowPhase: string | null;
  workflowPhaseIndex: number | null;
  workflowTaskIndex: number | null;
  workflowStrategy: string | null;
  status: string;
  outputPreview: string | null;
  error: string | null;
  tokenUsage: TokenUsageCounter | null;
  modelName: string | null;
  updatedAt: string;
}

export interface ExecutionPanelSession {
  executionId: string;
  taskId: string;
  workspaceId: string;
  threadId: string | null;
  featureId: string;
  title: string;
  description: string;
  panelKey: string | null;
  status: string;
  progress: number;
  message: string | null;
  currentStep: string | null;
  runtime: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error: string | null;
  action: string | null;
  tokenUsage: TokenUsageCounter | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  updatedAt: string;
  subagents: ExecutionPanelSubagent[];
}

export interface GroupedExecutionPanels {
  active: ExecutionPanelSession[];
  recent: ExecutionPanelSession[];
  completed: ExecutionPanelSession[];
}

export function normalizeExecutionTaskStatus(
  status: string,
): ExecutionCurrentTask["status"] {
  switch (status) {
    case "completed":
    case "failed_partial":
      return "completed";
    case "failed":
      return "failed";
    case "cancelled":
      return "cancelled";
    default:
      return "running";
  }
}

function nodeStateStatus(state: ExecutionNodeState | undefined): ExecutionTaskStage["status"] {
  if (state?.status === "completed") return "completed";
  if (state?.status === "running" || state?.status === "failed") return "running";
  return "pending";
}

function buildStages(
  execution: ExecutionRecord,
  feature:
    | Pick<WorkspaceFeature, "stages">
    | undefined,
): ExecutionTaskStage[] {
  const graphNodes = execution.graph_structure?.nodes ?? [];
  if (graphNodes.length > 0) {
    return graphNodes.map((node) => ({
      id: node.id,
      label: node.label || node.task || node.id,
      status: nodeStateStatus(execution.node_states[node.id]),
    }));
  }

  return (feature?.stages ?? [{ id: "run", label: "执行" }]).map((stage, index) => ({
    ...stage,
    status:
      execution.status === "completed" || execution.status === "failed_partial"
        ? "completed"
        : index === 0 && ACTIVE_EXECUTION_STATUSES.has(execution.status)
          ? "running"
          : "pending",
  }));
}

function readTokenCounter(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.max(0, Math.trunc(value));
  }
  if (typeof value === "string") {
    const parsed = Number.parseInt(value.trim(), 10);
    if (Number.isFinite(parsed)) {
      return Math.max(0, parsed);
    }
  }
  return 0;
}

function normalizeTokenUsage(value: unknown): TokenUsageCounter | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const candidate = value as Record<string, unknown>;
  const input = readTokenCounter(candidate.input_tokens);
  const output = readTokenCounter(candidate.output_tokens);
  const explicitTotal = readTokenCounter(candidate.total_tokens);
  const total = explicitTotal > 0 ? explicitTotal : input + output;
  if (input <= 0 && output <= 0 && total <= 0) {
    return null;
  }
  return {
    input_tokens: input,
    output_tokens: output,
    total_tokens: total,
  };
}

function aggregateNodeTokenUsage(
  nodeStates: Record<string, ExecutionNodeState>,
): TokenUsageCounter | null {
  let input = 0;
  let output = 0;
  let total = 0;
  for (const state of Object.values(nodeStates)) {
    const usage = normalizeTokenUsage(state.token_usage);
    if (!usage) continue;
    input += usage.input_tokens;
    output += usage.output_tokens;
    total += usage.total_tokens;
  }
  if (input <= 0 && output <= 0 && total <= 0) {
    return null;
  }
  return {
    input_tokens: input,
    output_tokens: output,
    total_tokens: total,
  };
}

function buildPanelSubagents(execution: ExecutionRecord): ExecutionPanelSubagent[] {
  const graphNodes = execution.graph_structure?.nodes ?? [];
  return graphNodes.map((node, index) => {
    const nodeState = execution.node_states[node.id] ?? {};
    return {
      id: node.id,
      threadId: execution.thread_id ?? "",
      subagentType: node.subagent_type ?? null,
      workflowPhase: node.phase ?? null,
      workflowPhaseIndex: typeof node.metadata?.phase_index === "number"
        ? node.metadata.phase_index
        : index,
      workflowTaskIndex: index,
      workflowStrategy: null,
      status: nodeState.status ?? "pending",
      outputPreview: nodeState.output_preview ?? null,
      error:
        typeof nodeState.output?.error === "string"
          ? nodeState.output.error
          : null,
      tokenUsage: normalizeTokenUsage(nodeState.token_usage),
      modelName: null,
      updatedAt: nodeState.completed_at || nodeState.started_at || execution.updated_at,
    };
  });
}

export function selectPreferredExecution(
  executions: ExecutionRecord[],
): ExecutionRecord | null {
  if (executions.length === 0) {
    return null;
  }
  const active = executions.find((execution) =>
    ACTIVE_EXECUTION_STATUSES.has(execution.status),
  );
  return active ?? executions[0] ?? null;
}

export function buildExecutionCurrentTask(
  execution: ExecutionRecord,
  feature:
    | Pick<WorkspaceFeature, "id" | "name" | "agent" | "agentLabel" | "stages">
    | undefined,
): ExecutionCurrentTask {
  const stages = buildStages(execution, feature);
  const currentStageIndex = Math.max(
    stages.findIndex((stage) => stage.status === "running"),
    0,
  );

  return {
    id: execution.id,
    featureId: execution.feature_id || "",
    status: normalizeExecutionTaskStatus(execution.status),
    agent: feature?.agent || execution.feature_id || execution.display_name || execution.id,
    agentLabel:
      feature?.agentLabel || feature?.name || execution.display_name || execution.feature_id || execution.id,
    thinking:
      execution.last_error ||
      execution.message ||
      execution.result_summary ||
      "",
    stages,
    currentStageIndex,
    startedAt: execution.started_at || execution.created_at || new Date().toISOString(),
    completedAt: execution.completed_at || undefined,
  };
}

export function adaptExecutionToPanelSession(
  execution: ExecutionRecord,
  feature?: Pick<WorkspaceFeature, "name" | "description" | "panel"> | null,
): ExecutionPanelSession {
  const tokenUsage =
    normalizeTokenUsage(execution.result?.task_report && typeof execution.result.task_report === "object"
      ? (execution.result.task_report as Record<string, unknown>).token_usage
      : null) ?? aggregateNodeTokenUsage(execution.node_states);

  return {
    executionId: execution.id,
    taskId: execution.id,
    workspaceId: execution.workspace_id || "",
    threadId: execution.thread_id ?? null,
    featureId: execution.feature_id || "",
    title: feature?.name || execution.display_name || execution.feature_id || execution.id,
    description:
      execution.result_summary ||
      execution.message ||
      feature?.description ||
      "执行已启动。",
    panelKey: feature?.panel ?? null,
    status:
      execution.status === "completed" || execution.status === "failed_partial"
        ? "success"
        : execution.status === "failed"
          ? "failed"
          : execution.status === "cancelled"
            ? "cancelled"
            : ACTIVE_EXECUTION_STATUSES.has(execution.status)
              ? "running"
              : "pending",
    progress: execution.progress ?? 0,
    message: execution.message || execution.result_summary || null,
    currentStep: null,
    runtime: execution.runtime_state ?? null,
    result: execution.result ?? null,
    error: execution.last_error || execution.error || null,
    action: null,
    tokenUsage,
    createdAt: execution.created_at || new Date().toISOString(),
    startedAt: execution.started_at || null,
    completedAt: execution.completed_at || null,
    updatedAt: execution.updated_at || execution.created_at || new Date().toISOString(),
    subagents: buildPanelSubagents(execution),
  };
}

export function groupExecutionPanels(
  sessions: ExecutionPanelSession[],
): GroupedExecutionPanels {
  const active = sessions.filter((session) =>
    session.status === "running" || session.status === "pending",
  );
  const completed = sessions.filter(
    (session) =>
      session.status === "success" ||
      session.status === "failed" ||
      session.status === "cancelled",
  );
  const completedSorted = [...completed].sort((left, right) =>
    right.updatedAt.localeCompare(left.updatedAt),
  );

  return {
    active,
    recent: completedSorted.slice(0, 3),
    completed: completedSorted.slice(3),
  };
}
