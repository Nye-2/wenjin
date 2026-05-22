import type { ExecutionRecord, ExecutionStatus } from "@/lib/api/types";
import type { RunRecord } from "@/lib/api/v2/runs";
import type { ResultCardData } from "@/stores/chat-store";

export type RunViewStatus =
  | "launching"
  | "queued"
  | "running"
  | "completed"
  | "failed_partial"
  | "failed"
  | "cancelled";

export type RunFailureCategory =
  | "launch_failed"
  | "queue_failed"
  | "node_failed"
  | "writeback_failed"
  | "commit_failed"
  | "unknown";

export type RunPrimaryAction =
  | "open_live"
  | "open_runs"
  | "open_prism"
  | "preview_results"
  | "retry"
  | "continue_chat";

export interface RunView {
  id: string;
  workspaceId: string;
  capabilityId?: string | null;
  title: string;
  status: RunViewStatus;
  summary: string;
  startedAt?: string | null;
  completedAt?: string | null;
  durationLabel?: string | null;
  progress?: number | null;
  nodeCount?: number;
  completedNodeCount?: number;
  failedNodeCount?: number;
  tokenUsage?: { input: number; output: number } | null;
  primarySurface?: "prism" | "rooms" | "sandbox" | "none";
  prismReviewCount?: number;
  hasPrismChanges: boolean;
  failureCategory?: RunFailureCategory | null;
  failureMessage?: string | null;
  actions: RunPrimaryAction[];
}

export function isTerminalRunStatus(status: RunViewStatus | string): boolean {
  return ["completed", "failed_partial", "failed", "cancelled"].includes(status);
}

export function runViewFromExecution(record: ExecutionRecord): RunView {
  const taskReport = taskReportFromResult(record.result);
  const tokenUsage =
    tokenUsageFromUnknown(taskReport?.token_usage) ??
    tokenUsageFromNodes(record.node_states);
  const prismReviewCount = countPrismReviewItems(
    record.review_items ?? reviewItemsFromTaskReport(taskReport),
  );
  const status = normalizeExecutionStatus(record.status);
  const failedNodeCount = countNodesByStatus(record, "failed");
  const completedNodeCount = countNodesByStatus(record, "completed");
  const nodeCount =
    record.graph_structure?.nodes.length ??
    Object.keys(record.node_states ?? {}).length;
  const failureMessage =
    record.last_error ??
    record.error ??
    stringValue(taskReport?.errors?.[0]?.error) ??
    null;
  const failureCategory =
    failureCategoryFromRecord(record, failedNodeCount, failureMessage);

  return {
    id: record.id,
    workspaceId: record.workspace_id ?? "",
    capabilityId: record.feature_id ?? stringValue(taskReport?.capability_id),
    title:
      record.display_name ??
      stringValue(taskReport?.capability_id) ??
      record.feature_id ??
      "Execution",
    status,
    summary:
      record.result_summary ??
      stringValue(taskReport?.narrative) ??
      record.message ??
      failureMessage ??
      statusSummary(status),
    startedAt: record.started_at ?? record.created_at,
    completedAt: record.completed_at ?? null,
    durationLabel: formatDuration(record.started_at ?? record.created_at, record.completed_at),
    progress: typeof record.progress === "number" ? record.progress : null,
    nodeCount,
    completedNodeCount,
    failedNodeCount,
    tokenUsage,
    primarySurface: prismReviewCount > 0 ? "prism" : "rooms",
    prismReviewCount,
    hasPrismChanges: prismReviewCount > 0,
    failureCategory,
    failureMessage,
    actions: actionsForRun({
      status,
      hasPrismChanges: prismReviewCount > 0,
      hasResults: Boolean(record.result || taskReport),
      failureCategory,
    }),
  };
}

export function runViewFromRunRecord(record: RunRecord, workspaceId: string): RunView {
  const status = normalizeRunRecordStatus(record.status);
  const prismReviewCount =
    typeof record.review_items_count === "number"
      ? record.review_items_count
      : record.has_prism_changes
        ? 1
        : 0;
  const failureMessage = record.failure_message ?? null;
  const failureCategory =
    record.failure_category ??
    (status === "failed" || status === "failed_partial" ? "unknown" : null);

  return {
    id: record.id,
    workspaceId: record.workspace_id ?? workspaceId,
    capabilityId: record.capability_id ?? null,
    title: record.capability_name || record.capability_id || "Execution",
    status,
    summary: record.summary || statusSummary(status),
    startedAt: record.started_at,
    completedAt: record.completed_at ?? null,
    durationLabel: formatDuration(record.started_at, record.completed_at ?? null),
    progress: typeof record.progress === "number" ? record.progress : null,
    tokenUsage: record.token_usage ?? null,
    primarySurface:
      record.primary_surface ??
      (prismReviewCount > 0 || record.has_prism_changes ? "prism" : "rooms"),
    prismReviewCount,
    hasPrismChanges: Boolean(record.has_prism_changes || prismReviewCount > 0),
    failureCategory,
    failureMessage,
    actions: actionsForRun({
      status,
      hasPrismChanges: Boolean(record.has_prism_changes || prismReviewCount > 0),
      hasResults: status === "completed" || status === "failed_partial",
      failureCategory,
    }),
  };
}

export function runViewFromResultCard(
  data: ResultCardData,
  workspaceId: string,
): RunView {
  const status = normalizeRunRecordStatus(data.status);
  const prismReviewCount = countPrismReviewItems(data.review_items ?? []);
  const failureMessage = data.errors?.[0]?.message ?? null;
  const failureCategory =
    status === "failed_partial" || status === "failed"
      ? data.errors?.length
        ? "node_failed"
        : "unknown"
      : null;

  return {
    id: data.execution_id,
    workspaceId,
    capabilityId: data.capability_name ?? null,
    title: data.capability_name ?? "Execution",
    status,
    summary: data.narrative ?? failureMessage ?? statusSummary(status),
    completedAt: null,
    durationLabel:
      typeof data.duration_seconds === "number"
        ? formatSeconds(data.duration_seconds)
        : null,
    tokenUsage: tokenUsageFromUnknown(data.token_usage),
    primarySurface: prismReviewCount > 0 ? "prism" : "rooms",
    prismReviewCount,
    hasPrismChanges: prismReviewCount > 0,
    failureCategory,
    failureMessage,
    actions: actionsForRun({
      status,
      hasPrismChanges: prismReviewCount > 0,
      hasResults: Boolean(data.outputs?.length || data.review_items?.length),
      failureCategory,
    }),
  };
}

export function mergeRunViews(
  live: RunView | null,
  historical: RunView | null,
): RunView {
  if (!live && !historical) {
    throw new Error("mergeRunViews requires at least one RunView");
  }
  if (!live) return historical!;
  if (!historical) return live;
  return {
    ...historical,
    ...live,
    summary: live.summary || historical.summary,
    startedAt: live.startedAt ?? historical.startedAt,
    completedAt: live.completedAt ?? historical.completedAt,
    durationLabel: live.durationLabel ?? historical.durationLabel,
    tokenUsage: live.tokenUsage ?? historical.tokenUsage,
    primarySurface: live.primarySurface ?? historical.primarySurface,
    prismReviewCount: Math.max(
      live.prismReviewCount ?? 0,
      historical.prismReviewCount ?? 0,
    ),
    hasPrismChanges: live.hasPrismChanges || historical.hasPrismChanges,
    failureCategory: live.failureCategory ?? historical.failureCategory,
    failureMessage: live.failureMessage ?? historical.failureMessage,
    actions: Array.from(new Set([...live.actions, ...historical.actions])),
  };
}

function normalizeExecutionStatus(status: ExecutionStatus): RunViewStatus {
  if (status === "pending") return "queued";
  if (status === "cancelling") return "running";
  if (status === "awaiting_user_input") return "running";
  return normalizeRunRecordStatus(status);
}

function normalizeRunRecordStatus(status: string): RunViewStatus {
  if (status === "completed") return "completed";
  if (status === "failed_partial") return "failed_partial";
  if (status === "failed") return "failed";
  if (status === "cancelled") return "cancelled";
  if (status === "pending" || status === "queued") return "queued";
  if (status === "launching") return "launching";
  return "running";
}

function taskReportFromResult(
  result: Record<string, unknown> | null | undefined,
): Record<string, any> | null {
  const candidate = result?.task_report;
  if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) {
    return candidate as Record<string, any>;
  }
  return null;
}

function reviewItemsFromTaskReport(
  taskReport: Record<string, any> | null,
): unknown[] {
  return Array.isArray(taskReport?.review_items) ? taskReport.review_items : [];
}

function countPrismReviewItems(items: unknown[]): number {
  return items.filter((item) => {
    if (!item || typeof item !== "object") return false;
    const entry = item as Record<string, unknown>;
    return (
      entry.kind === "prism_file_change" ||
      entry.target_domain === "prism" ||
      (entry.target &&
        typeof entry.target === "object" &&
        (entry.target as Record<string, unknown>).kind === "prism_file_change")
    );
  }).length;
}

function tokenUsageFromUnknown(
  value: unknown,
): { input: number; output: number } | null {
  if (!value || typeof value !== "object") return null;
  const usage = value as Record<string, unknown>;
  const input = Number(usage.input ?? usage.input_tokens ?? 0);
  const output = Number(usage.output ?? usage.output_tokens ?? 0);
  if (!Number.isFinite(input) || !Number.isFinite(output)) return null;
  if (input === 0 && output === 0) return null;
  return { input, output };
}

function tokenUsageFromNodes(
  nodes: ExecutionRecord["node_states"],
): { input: number; output: number } | null {
  let input = 0;
  let output = 0;
  for (const node of Object.values(nodes ?? {})) {
    const usage = tokenUsageFromUnknown(node.token_usage);
    if (!usage) continue;
    input += usage.input;
    output += usage.output;
  }
  return input || output ? { input, output } : null;
}

function countNodesByStatus(record: ExecutionRecord, status: string): number {
  return Object.values(record.node_states ?? {}).filter((node) => node.status === status).length;
}

function failureCategoryFromRecord(
  record: ExecutionRecord,
  failedNodeCount: number,
  failureMessage: string | null,
): RunFailureCategory | null {
  if (record.status !== "failed" && record.status !== "failed_partial") {
    return null;
  }
  const lower = (failureMessage ?? "").toLowerCase();
  if (lower.includes("queue") || lower.includes("celery") || lower.includes("dispatch")) {
    return "queue_failed";
  }
  if (lower.includes("writeback") || lower.includes("write back")) {
    return "writeback_failed";
  }
  if (failedNodeCount > 0 || record.status === "failed_partial") {
    return "node_failed";
  }
  return "unknown";
}

function actionsForRun({
  status,
  hasPrismChanges,
  hasResults,
  failureCategory,
}: {
  status: RunViewStatus;
  hasPrismChanges: boolean;
  hasResults: boolean;
  failureCategory?: RunFailureCategory | null;
}): RunPrimaryAction[] {
  const actions: RunPrimaryAction[] = ["open_live", "open_runs"];
  if (hasPrismChanges) actions.push("open_prism");
  if (hasResults) actions.push("preview_results");
  if (status === "completed" || status === "failed_partial") {
    actions.push("continue_chat");
  }
  if (status === "failed" || failureCategory === "queue_failed") {
    actions.push("retry");
  }
  return Array.from(new Set(actions));
}

function statusSummary(status: RunViewStatus): string {
  if (status === "launching") return "正在启动 Lead Agent...";
  if (status === "queued") return "已进入执行队列。";
  if (status === "running") return "Lead Agent 正在执行。";
  if (status === "completed") return "执行已完成。";
  if (status === "failed_partial") return "执行部分完成，需要查看失败节点。";
  if (status === "failed") return "执行失败。";
  return "执行已取消。";
}

function formatDuration(
  startedAt?: string | null,
  completedAt?: string | null,
): string | null {
  if (!startedAt) return null;
  const started = Date.parse(startedAt);
  if (!Number.isFinite(started)) return null;
  const ended = completedAt ? Date.parse(completedAt) : Date.now();
  if (!Number.isFinite(ended)) return null;
  const seconds = Math.max(0, Math.round((ended - started) / 1000));
  return formatSeconds(seconds);
}

function formatSeconds(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
