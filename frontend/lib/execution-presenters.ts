import type {
  ExecutionSession,
  TokenUsageCounter,
  WorkspaceFeature,
} from "@/lib/api";
import { ACTIVE_EXECUTION_STATUSES } from "@/lib/execution-status";
import type { TaskRuntimeState } from "@/lib/task-runtime";

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
  runtime: TaskRuntimeState | null;
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

export interface GroupedExecutionSessions {
  active: ExecutionPanelSession[];
  recent: ExecutionPanelSession[];
  completed: ExecutionPanelSession[];
}

export function normalizeExecutionTaskStatus(
  status: string
): ExecutionCurrentTask["status"] {
  switch (status) {
    case "completed":
    case "failed_partial":
      return "completed";
    case "failed":
    case "advisory":
      return "failed";
    case "cancelled":
      return "cancelled";
    default:
      return "running";
  }
}

export function selectPreferredExecution(
  sessions: ExecutionSession[]
): ExecutionSession | null {
  if (sessions.length === 0) {
    return null;
  }
  const active = sessions.find(
    (session) =>
      ACTIVE_EXECUTION_STATUSES.has(session.status as never)
  );
  return active ?? sessions[0] ?? null;
}

export function buildExecutionCurrentTask(
  execution: ExecutionSession,
  feature:
    | Pick<WorkspaceFeature, "id" | "name" | "agent" | "agentLabel" | "stages">
    | undefined
): ExecutionCurrentTask {
  const rawRuntime =
    execution.runtime_snapshot && typeof execution.runtime_snapshot === "object"
      ? execution.runtime_snapshot
      : null;
  const runtime = rawRuntime as
    | {
        current_phase?: string;
        phases?: { id: string; label: string; status?: string }[];
      }
    | null;
  const normalizedStatus = normalizeExecutionTaskStatus(execution.status);
  const phases =
    Array.isArray(runtime?.phases) && runtime?.phases.length
      ? runtime.phases.map((phase) => ({
          id: phase.id,
          label: phase.label,
          status:
            phase.status === "completed"
              ? ("completed" as const)
              : phase.status === "running"
                ? ("running" as const)
                : ("pending" as const),
        }))
      : (feature?.stages ?? [{ id: "run", label: "执行" }]).map((phase, index) => ({
          ...phase,
          status:
            normalizedStatus === "completed"
              ? ("completed" as const)
              : normalizedStatus === "failed"
                ? index === 0
                  ? ("running" as const)
                  : ("pending" as const)
                : index === 0
                  ? ("running" as const)
                  : ("pending" as const),
        }));

  const currentPhaseId =
    execution.current_step ??
    runtime?.current_phase ??
    null;
  const currentStageIndex = currentPhaseId
    ? Math.max(
        phases.findIndex((phase) => phase.id === currentPhaseId),
        0
      )
    : Math.max(
        phases.findIndex((phase) => phase.status === "running"),
        0
      );

  return {
    id: execution.primary_task_id || execution.id,
    featureId: execution.feature_id,
    status: normalizedStatus,
    agent: feature?.agent || execution.feature_id,
    agentLabel: feature?.agentLabel || feature?.name || execution.feature_id,
    thinking:
      execution.last_error ||
      execution.task_message ||
      execution.result_summary ||
      execution.launch_message ||
      "",
    stages: phases,
    currentStageIndex,
    startedAt: execution.started_at || execution.created_at || new Date().toISOString(),
    completedAt: execution.completed_at || undefined,
  };
}

function normalizeWorkflowIndex(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.max(0, Math.trunc(value));
  }
  if (typeof value === "string") {
    const parsed = Number.parseInt(value.trim(), 10);
    if (Number.isFinite(parsed)) {
      return Math.max(0, parsed);
    }
  }
  return null;
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

function aggregateSubagentTokenUsage(
  subagents: ExecutionPanelSubagent[]
): TokenUsageCounter | null {
  if (subagents.length === 0) {
    return null;
  }
  let input = 0;
  let output = 0;
  let total = 0;
  for (const subagent of subagents) {
    if (!subagent.tokenUsage) {
      continue;
    }
    input += subagent.tokenUsage.input_tokens;
    output += subagent.tokenUsage.output_tokens;
    total += subagent.tokenUsage.total_tokens;
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

export function adaptExecutionToPanelSession(
  execution: ExecutionSession,
  feature?: Pick<WorkspaceFeature, "name" | "description" | "panel"> | null
): ExecutionPanelSession {
  const runtime =
    execution.runtime_snapshot && typeof execution.runtime_snapshot === "object"
      ? (execution.runtime_snapshot as TaskRuntimeState)
      : null;
  const currentPhase =
    execution.current_step ||
    (runtime &&
    typeof runtime === "object" &&
    typeof (runtime as Record<string, unknown>).current_phase === "string"
      ? String((runtime as Record<string, unknown>).current_phase)
      : null);
  const normalizedSubagents: ExecutionPanelSubagent[] = Array.isArray(execution.subagents)
    ? execution.subagents.map((subagent) => ({
        id: subagent.task_id,
        threadId: subagent.thread_id,
        subagentType:
          typeof subagent.subagent_type === "string"
            ? subagent.subagent_type
            : null,
        workflowPhase:
          typeof subagent.workflow_phase === "string"
            ? subagent.workflow_phase
            : null,
        workflowPhaseIndex: normalizeWorkflowIndex(
          subagent.workflow_phase_index
        ),
        workflowTaskIndex: normalizeWorkflowIndex(
          subagent.workflow_task_index
        ),
        workflowStrategy:
          typeof subagent.workflow_strategy === "string"
            ? subagent.workflow_strategy
            : null,
        status: subagent.status,
        outputPreview:
          typeof subagent.output_preview === "string"
            ? subagent.output_preview
            : null,
        error:
          typeof subagent.error === "string" ? subagent.error : null,
        tokenUsage: normalizeTokenUsage(subagent.token_usage),
        modelName:
          typeof subagent.model_name === "string" && subagent.model_name.trim()
            ? subagent.model_name.trim()
            : null,
        updatedAt: subagent.updated_at || new Date().toISOString(),
      }))
    : [];
  const tokenUsage =
    normalizeTokenUsage(execution.token_usage) ??
    aggregateSubagentTokenUsage(normalizedSubagents);

  return {
    executionId: execution.id,
    taskId: execution.primary_task_id || execution.id,
    workspaceId: execution.workspace_id,
    threadId: execution.thread_id ?? null,
    featureId: execution.feature_id,
    title: feature?.name || execution.feature_id,
    description:
      execution.result_summary ||
      execution.task_message ||
      execution.launch_message ||
      feature?.description ||
      "执行会话已启动。",
    panelKey: feature?.panel ?? null,
    status:
      execution.status === "completed" || execution.status === "failed_partial"
        ? "success"
        : execution.status === "failed" || execution.status === "advisory"
          ? "failed"
          : execution.status === "cancelled"
            ? "cancelled"
          : ACTIVE_EXECUTION_STATUSES.has(execution.status as never)
            ? "running"
            : "pending",
    progress: execution.progress ?? 0,
    message:
      execution.task_message ||
      execution.result_summary ||
      execution.launch_message ||
      null,
    currentStep: currentPhase,
    runtime,
    result:
      execution.result_payload && typeof execution.result_payload === "object"
        ? execution.result_payload
        : null,
    error: execution.last_error || null,
    action: null,
    tokenUsage,
    createdAt: execution.created_at || new Date().toISOString(),
    startedAt: execution.started_at || null,
    completedAt: execution.completed_at || null,
    updatedAt: execution.updated_at || execution.created_at || new Date().toISOString(),
    subagents: normalizedSubagents,
  };
}

export function groupExecutionSessions(
  sessions: ExecutionPanelSession[]
): GroupedExecutionSessions {
  const active = sessions.filter(
    (session) => ACTIVE_EXECUTION_STATUSES.has(session.status as never)
  );
  const completed = sessions.filter(
    (session) =>
      session.status === "success" ||
      session.status === "failed" ||
      session.status === "cancelled"
  );
  const completedSorted = [...completed].sort((left, right) =>
    right.updatedAt.localeCompare(left.updatedAt)
  );

  return {
    active,
    recent: completedSorted.slice(0, 3),
    completed: completedSorted.slice(3),
  };
}
