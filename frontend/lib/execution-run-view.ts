import type {
  ExecutionGraphNode,
  ExecutionNodeState,
  ExecutionRecord,
  ExecutionStatus,
} from "@/lib/api/types";
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

export interface RunViewTeamMember {
  id: string;
  templateId?: string | null;
  displayName: string;
  status: string;
  effectiveTools: string[];
  effectiveSkills: string[];
  activityLabel?: string;
  artifactCount?: number;
  debugToolCount?: number;
}

export interface RunViewQualityGate {
  id: string;
  status: "pass" | "warning" | "fail";
  severity?: "low" | "medium" | "high";
  nextAction?: string | null;
}

export interface RunViewTeam {
  mode: "team_kernel";
  members: RunViewTeamMember[];
  qualityGates: RunViewQualityGate[];
}

export interface RunProgressItem {
  id: string;
  title: string;
  phaseTitle: string;
  status: string;
  detail: string | null;
  technicalName: string;
  startedAt?: string | null;
  completedAt?: string | null;
  toolCount: number;
  hasInput: boolean;
  hasOutput: boolean;
}

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
  sandboxReviewCount?: number;
  hasPrismChanges: boolean;
  hasSandboxArtifacts?: boolean;
  failureCategory?: RunFailureCategory | null;
  failureMessage?: string | null;
  team?: RunViewTeam | null;
  actions: RunPrimaryAction[];
}

type TaskReportProjection = Record<string, unknown> & {
  errors?: Array<Record<string, unknown>>;
  review_items?: unknown[];
};

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
  const sandboxReviewCount = countSandboxReviewItems(
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
  const team = teamViewFromExecution(record);

  return {
    id: record.id,
    workspaceId: record.workspace_id ?? "",
    capabilityId: record.feature_id ?? stringValue(taskReport?.capability_id),
    title: runTitleFromExecution(record, taskReport),
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
    primarySurface:
      prismReviewCount > 0 ? "prism" : sandboxReviewCount > 0 ? "sandbox" : "rooms",
    prismReviewCount,
    sandboxReviewCount,
    hasPrismChanges: prismReviewCount > 0,
    hasSandboxArtifacts: sandboxReviewCount > 0,
    failureCategory,
    failureMessage,
    team,
    actions: actionsForRun({
      status,
      hasPrismChanges: prismReviewCount > 0,
      hasResults: Boolean(record.result || taskReport || sandboxReviewCount > 0),
      failureCategory,
    }),
  };
}

export function buildRunProgressItems(record: ExecutionRecord): RunProgressItem[] {
  const nodes = record.graph_structure?.nodes ?? [];
  if (nodes.length === 0) {
    return Object.entries(record.node_states ?? {}).map(([id, state]) =>
      runProgressItemFromNode(
        {
          id,
          type: state.node_type ?? "node",
          label: state.label ?? undefined,
        },
        state,
      ),
    );
  }
  return nodes.map((node) =>
    runProgressItemFromNode(node, record.node_states?.[node.id] ?? null),
  );
}

export function executionNodeDisplayName(
  node: Pick<
    ExecutionGraphNode,
    "id" | "type" | "label" | "task" | "subagent_type" | "metadata"
  > | null,
  state?: ExecutionNodeState | null,
): string {
  const metadata = objectValue(state?.node_metadata) ?? objectValue(node?.metadata);
  const candidates = [
    metadata?.display_name,
    metadata?.role_name,
    metadata?.persona_name,
    metadata?.agent_name,
    state?.label,
    node?.label,
    node?.task,
  ];
  for (const candidate of candidates) {
    const value = stringValue(candidate);
    if (value && !looksTechnicalName(value)) {
      return value;
    }
  }

  const technicalCandidate =
    stringValue(metadata?.template_id) ??
    stringValue(node?.subagent_type) ??
    stringValue(node?.task) ??
    stringValue(node?.label) ??
    stringValue(node?.id);
  return humanizeTechnicalName(
    technicalCandidate,
    stringValue(state?.node_type) ?? stringValue(node?.type),
  );
}

export function executionPhaseDisplayName(phaseName?: string | null): string {
  const raw = stringValue(phaseName);
  if (!raw || raw === "default") return "执行过程";
  if (containsCjk(raw) && !looksTechnicalName(raw)) return raw;

  const normalized = normalizeTechnicalName(raw);
  const phaseLabels: Array<[RegExp, string]> = [
    [/research|retriev|search|scout|survey/, "资料检索"],
    [/synth|literature|matrix|gap/, "文献综合"],
    [/plan|outline|strategy/, "规划"],
    [/writ|draft|compose/, "写作"],
    [/review|critic|quality|gate|verify|check/, "质量检查"],
    [/experiment|sandbox|code|compute|analysis/, "实验执行"],
    [/commit|save|final|deliver/, "结果整理"],
  ];
  return phaseLabels.find(([pattern]) => pattern.test(normalized))?.[1] ?? "执行过程";
}

export function runViewFromRunRecord(record: RunRecord, workspaceId: string): RunView {
  const status = normalizeRunRecordStatus(record.status);
  const prismReviewCount =
    typeof record.review_items_count === "number"
      ? record.review_items_count
      : record.has_prism_changes
        ? 1
        : 0;
  const sandboxReviewCount = record.primary_surface === "sandbox" ? 1 : 0;
  const failureMessage = record.failure_message ?? null;
  const failureCategory =
    record.failure_category ??
    (status === "failed" || status === "failed_partial" ? "unknown" : null);

  return {
    id: record.id,
    workspaceId: record.workspace_id ?? workspaceId,
    capabilityId: record.capability_id ?? null,
    title: humanizeCapabilityName(record.capability_name || record.capability_id) ?? "Execution",
    status,
    summary: record.summary || statusSummary(status),
    startedAt: record.started_at,
    completedAt: record.completed_at ?? null,
    durationLabel: formatDuration(record.started_at, record.completed_at ?? null),
    progress: typeof record.progress === "number" ? record.progress : null,
    tokenUsage: record.token_usage ?? null,
    primarySurface:
      record.primary_surface ??
      (prismReviewCount > 0 || record.has_prism_changes
        ? "prism"
        : sandboxReviewCount > 0
          ? "sandbox"
          : "rooms"),
    prismReviewCount,
    sandboxReviewCount,
    hasPrismChanges: Boolean(record.has_prism_changes || prismReviewCount > 0),
    hasSandboxArtifacts: sandboxReviewCount > 0,
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
  const sandboxReviewCount = countSandboxReviewItems(data.review_items ?? []);
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
    title: humanizeCapabilityName(data.capability_name) ?? "Execution",
    status,
    summary: data.narrative ?? failureMessage ?? statusSummary(status),
    completedAt: null,
    durationLabel:
      typeof data.duration_seconds === "number"
        ? formatSeconds(data.duration_seconds)
        : null,
    tokenUsage: tokenUsageFromUnknown(data.token_usage),
    primarySurface:
      prismReviewCount > 0 ? "prism" : sandboxReviewCount > 0 ? "sandbox" : "rooms",
    prismReviewCount,
    sandboxReviewCount,
    hasPrismChanges: prismReviewCount > 0,
    hasSandboxArtifacts: sandboxReviewCount > 0,
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
    sandboxReviewCount: Math.max(
      live.sandboxReviewCount ?? 0,
      historical.sandboxReviewCount ?? 0,
    ),
    hasPrismChanges: live.hasPrismChanges || historical.hasPrismChanges,
    hasSandboxArtifacts: Boolean(live.hasSandboxArtifacts || historical.hasSandboxArtifacts),
    failureCategory: live.failureCategory ?? historical.failureCategory,
    failureMessage: live.failureMessage ?? historical.failureMessage,
    team: live.team ?? historical.team,
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
): TaskReportProjection | null {
  const candidate = result?.task_report;
  if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) {
    return candidate as TaskReportProjection;
  }
  return null;
}

function reviewItemsFromTaskReport(
  taskReport: TaskReportProjection | null,
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

function countSandboxReviewItems(items: unknown[]): number {
  return items.filter((item) => {
    if (!item || typeof item !== "object") return false;
    const entry = item as Record<string, unknown>;
    return (
      entry.kind === "sandbox_artifact" ||
      entry.target_domain === "sandbox" ||
      (entry.target &&
        typeof entry.target === "object" &&
        (entry.target as Record<string, unknown>).kind === "sandbox_artifact")
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

function teamViewFromExecution(record: ExecutionRecord): RunViewTeam | null {
  const isTeamMode = record.graph_structure?.mode === "team_kernel";
  const members = teamMembersFromNodeStates(
    record.node_states,
    record.graph_structure?.nodes,
  );
  const qualityGates = teamQualityGatesFromRuntimeState(record.runtime_state);
  if (!isTeamMode && members.length === 0 && qualityGates.length === 0) {
    return null;
  }
  return {
    mode: "team_kernel",
    members,
    qualityGates,
  };
}

function teamMembersFromNodeStates(
  nodes: ExecutionRecord["node_states"],
  graphNodes?: ExecutionGraphNode[],
): RunViewTeamMember[] {
  const members: RunViewTeamMember[] = [];
  for (const [id, rawNode] of Object.entries(nodes ?? {})) {
    const node = rawNode as Record<string, unknown>;
    const metadata = objectValue(node.node_metadata);
    const nodeType = stringValue(node.node_type);
    if (nodeType !== "agent_invocation" && metadata?.team !== true) {
      continue;
    }
    const templateId = stringValue(metadata?.template_id);
    const displayName = executionNodeDisplayName(
      {
        id,
        type: nodeType ?? "agent_invocation",
        label: stringValue(node.label) ?? undefined,
        task: templateId ?? undefined,
      },
      rawNode,
    );
    const activity = harnessActivityFromNodeState(rawNode);
    const debugToolCount = rawNode.tool_calls?.length ?? 0;
    members.push({
      id,
      templateId,
      displayName,
      status: stringValue(node.status) ?? "pending",
      effectiveTools: stringArrayValue(metadata?.effective_tools),
      effectiveSkills: stringArrayValue(metadata?.effective_skills),
      ...(activity.label ? { activityLabel: activity.label } : {}),
      ...(activity.artifactCount > 0 ? { artifactCount: activity.artifactCount } : {}),
      ...(debugToolCount > 0 ? { debugToolCount } : {}),
    });
  }
  if (graphNodes?.length) {
    const graphOrder = new Map(
      graphNodes.map((node, index) => [node.id, index]),
    );
    members.sort((left, right) => {
      const leftIndex = graphOrder.get(left.id) ?? Number.MAX_SAFE_INTEGER;
      const rightIndex = graphOrder.get(right.id) ?? Number.MAX_SAFE_INTEGER;
      if (leftIndex !== rightIndex) return leftIndex - rightIndex;
      return left.id.localeCompare(right.id);
    });
  }
  return members;
}

function teamQualityGatesFromRuntimeState(
  runtimeState: Record<string, unknown> | null | undefined,
): RunViewQualityGate[] {
  const direct = arrayValue(runtimeState?.quality_gates);
  const nested = arrayValue(objectValue(runtimeState?.team)?.quality_gates);
  const qualityGates: RunViewQualityGate[] = [];
  for (const rawGate of [...direct, ...nested]) {
    const gate = objectValue(rawGate);
    if (!gate) continue;
    const id = stringValue(gate.gate_id) ?? stringValue(gate.id);
    if (!id) continue;
    const severity = normalizeQualityGateSeverity(gate.severity);
    qualityGates.push({
      id,
      status: normalizeQualityGateStatus(gate.status),
      ...(severity ? { severity } : {}),
      nextAction: stringValue(gate.next_action) ?? stringValue(gate.nextAction),
    });
  }
  return qualityGates;
}

function normalizeQualityGateStatus(value: unknown): RunViewQualityGate["status"] {
  if (value === "pass" || value === "warning" || value === "fail") return value;
  return "warning";
}

function normalizeQualityGateSeverity(
  value: unknown,
): RunViewQualityGate["severity"] {
  if (value === "low" || value === "medium" || value === "high") return value;
  return undefined;
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

function runTitleFromExecution(
  record: ExecutionRecord,
  taskReport: TaskReportProjection | null,
): string {
  const explicit = stringValue(record.display_name);
  if (explicit) return explicit;
  return (
    humanizeCapabilityName(
      stringValue(taskReport?.capability_name) ??
        stringValue(taskReport?.capability_id) ??
        stringValue(record.feature_id),
    ) ?? "Execution"
  );
}

function runProgressItemFromNode(
  node: ExecutionGraphNode,
  state: ExecutionNodeState | null,
): RunProgressItem {
  return {
    id: node.id,
    title: executionNodeDisplayName(node, state),
    phaseTitle: executionPhaseDisplayName(node.phase),
    status: state?.status ?? "pending",
    detail: progressDetailFromNodeState(state),
    technicalName: node.id,
    startedAt: state?.started_at ?? null,
    completedAt: state?.completed_at ?? null,
    toolCount: state?.tool_calls?.length ?? 0,
    hasInput: Boolean(state?.input),
    hasOutput: Boolean(state?.output),
  };
}

function progressDetailFromNodeState(state: ExecutionNodeState | null): string | null {
  if (!state) return null;
  if (state.error) return trimForDisplay(state.error, 120);
  const harnessActivity = harnessActivityFromNodeState(state).label;
  if (harnessActivity) return harnessActivity;
  if (state.thinking) return trimForDisplay(state.thinking, 140);
  if (state.output_preview) return trimForDisplay(state.output_preview, 140);
  return null;
}

function harnessActivityFromNodeState(
  state: ExecutionNodeState | null | undefined,
): { label: string | null; artifactCount: number } {
  const harness = objectValue(objectValue(state?.node_metadata)?.harness);
  if (!harness) return { label: null, artifactCount: 0 };
  const journalSummary = objectValue(harness.run_journal_summary);
  const journalLabel = stringValue(journalSummary?.summary);
  if (journalLabel) {
    const artifactCount = Number(journalSummary?.artifact_count ?? 0);
    return {
      label: trimForDisplay(journalLabel, 120),
      artifactCount: Number.isFinite(artifactCount) && artifactCount > 0 ? artifactCount : 0,
    };
  }
  const sandboxSummary = objectValue(harness.sandbox_execution_summary);
  const failureSummary = objectValue(harness.tool_failure_summary);
  const fileSummary = objectValue(harness.file_change_summary);
  const failedTools = Number(failureSummary?.total_failed_calls ?? 0);
  if (Number.isFinite(failedTools) && failedTools > 0) {
    return { label: "工具异常待处理", artifactCount: 0 };
  }
  const failedPythonRuns = Number(sandboxSummary?.failed_python_runs ?? 0);
  if (Number.isFinite(failedPythonRuns) && failedPythonRuns > 0) {
    return { label: "实验需要修订", artifactCount: 0 };
  }
  const artifactCount = Number(sandboxSummary?.generated_artifact_count ?? 0);
  if (Number.isFinite(artifactCount) && artifactCount > 0) {
    return {
      label: `已生成 ${artifactCount} 个产物`,
      artifactCount,
    };
  }
  const pythonRuns = Number(sandboxSummary?.python_runs ?? 0);
  if (Number.isFinite(pythonRuns) && pythonRuns > 0) {
    return {
      label: state?.status === "running" ? "正在运行实验" : "已完成实验",
      artifactCount: 0,
    };
  }
  const changedPaths = arrayValue(fileSummary?.changed_paths).length;
  if (changedPaths > 0) {
    return { label: `已更新 ${changedPaths} 个文件`, artifactCount: 0 };
  }
  return { label: null, artifactCount: 0 };
}

function humanizeCapabilityName(value: string | null | undefined): string | null {
  const raw = stringValue(value);
  if (!raw) return null;
  if (!looksTechnicalName(raw)) return raw;

  const normalized = normalizeTechnicalName(raw);
  const rules: Array<[RegExp, string]> = [
    [/literature.*position|position.*innovation|gap.*contribution|sci_literature_positioning/, "文献定位与创新点"],
    [/reproduc|replication/, "可复现性检查"],
    [/journal|venue|submission|submit/, "投稿策略"],
    [/manuscript|draft|writing|writer/, "论文写作"],
    [/experiment|empirical|result/, "实验实证结果包"],
    [/outline|framework|structure/, "论文框架"],
    [/review.*package|workspace.*review|synthesis/, "研究综述包"],
    [/patent/, "专利工作流"],
    [/proposal|grant/, "项目申报"],
    [/software.*copyright|copyright/, "软著材料"],
  ];
  const matched = rules.find(([pattern]) => pattern.test(normalized));
  if (matched) return matched[1];

  return raw
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function humanizeTechnicalName(
  value: string | null,
  nodeType?: string | null,
): string {
  const normalized = normalizeTechnicalName(value ?? "");
  const rules: Array<[RegExp, string]> = [
    [/literature.*(synth|matrix|gap)|synth.*literature/, "文献综合专家"],
    [/research.*scholar|scholar|literature.*expert/, "文献专家"],
    [/(research|paper|semantic|scholar|literature).*(scout|search|retriev|collect|finder)|scout/, "文献检索专家"],
    [/critical|reviewer|critic|quality.*review|peer.*review/, "质量审阅专家"],
    [/quality|gate|verify|validation|checker/, "质量检查"],
    [/experiment|runner|analysis|compute|simulation/, "实验工程师"],
    [/sandbox.*(setup|prepare|env)|env.*setup|environment/, "实验环境准备"],
    [/(code|coder|developer|programmer|engineer)/, "代码工程师"],
    [/writ|draft|compose|editor/, "写作助理"],
    [/outline|planner|strategy|plan/, "规划专家"],
    [/citation|reference|bibliography/, "引文整理专家"],
    [/data|dataset|statistic/, "数据分析师"],
    [/patent/, "专利策略师"],
    [/proposal|grant/, "项目申报顾问"],
  ];
  const matched = rules.find(([pattern]) => pattern.test(normalized));
  if (matched) return matched[1];
  if (nodeType === "agent_invocation") return "团队成员";
  if (nodeType === "tool_invocation" || nodeType === "tool") return "工具执行";
  return "工作步骤";
}

function looksTechnicalName(value: string): boolean {
  if (containsCjk(value)) return false;
  const trimmed = value.trim();
  if (!trimmed) return false;
  return (
    /^[a-z0-9_.:-]+$/i.test(trimmed) ||
    /(^|[_\-.])v\d+($|[_\-.])/.test(trimmed) ||
    /__\d+$/.test(trimmed)
  );
}

function normalizeTechnicalName(value: string): string {
  return value
    .trim()
    .replace(/^step[_-]?\d+[_-]?/i, "")
    .replace(/__\d+$/i, "")
    .replace(/\.v\d+.*$/i, "")
    .replace(/[^a-z0-9]+/gi, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
}

function containsCjk(value: string): boolean {
  return /[\u3400-\u9fff]/.test(value);
}

function trimForDisplay(value: string, maxLength: number): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, maxLength - 1)}...`;
}

function statusSummary(status: RunViewStatus): string {
  if (status === "launching") return "正在启动研究团队...";
  if (status === "queued") return "已进入执行队列。";
  if (status === "running") return "问津正在处理任务。";
  if (status === "completed") return "执行已完成。";
  if (status === "failed_partial") return "执行部分完成，需要查看失败步骤。";
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

function objectValue(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stringArrayValue(value: unknown): string[] {
  return arrayValue(value)
    .map((item) => stringValue(item))
    .filter((item): item is string => Boolean(item));
}
