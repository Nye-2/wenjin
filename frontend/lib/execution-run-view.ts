import type {
  ExecutionGraphNode,
  ExecutionNodeState,
  ExecutionRecord,
  ExecutionStatus,
  WorkspacePrismReviewItem,
} from "@/lib/api/types";
import type { RunRecord } from "@/lib/api/v2/runs";
import {
  readCommitStateFromResult,
  type ExecutionCommitState,
} from "@/lib/execution-commit";
import {
  recoverableOutputRefCount,
  safeRuntimeText,
} from "@/lib/runtime-payload-safety";
import {
  buildWorkspaceResultPreviewsFromOutputs,
  buildWorkspaceResultPreviewsFromReviewItems,
  type WorkspaceResultPreview,
} from "@/lib/workspace-result-preview";
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

export interface RunViewExpertProfile {
  publicName: string;
  shortName?: string;
  roleTitle: string;
  avatarLabel: string;
  tone: "professional" | "witty_professional";
  tagline?: string;
  statusPhrase?: string;
}

export interface RunViewTeamMemberSnapshot {
  id: string;
  status: "queued" | "running" | "blocked" | "completed" | "failed";
  updateKind: "progress" | "finding" | "risk" | "decision" | "output" | "question";
  stageLabel: string;
  headline: string;
  body: string;
  chips: Array<{ label: string; value?: string; tone?: string }>;
  evidenceRefs: Array<{ label: string; type: string; refId?: string; path?: string; count?: number }>;
  outputRefs: Array<{ label: string; kind: string; refId?: string; previewItemId?: string; path?: string; status?: string }>;
  nextStep?: string;
  confidence?: "low" | "medium" | "high";
  createdAt: string;
}

export interface RunViewTeamMemberPreviewItem {
  id: string;
  ownerMemberId: string;
  title: string;
  subtitle?: string;
  kind: string;
  summary: string;
  status: "draft" | "ready" | "saved";
  payloadRef?: string;
  sourceRefs: Array<{ label: string; type: string; refId?: string; path?: string }>;
  createdAt: string;
}

export interface RunViewTeamMember {
  id: string;
  templateId?: string | null;
  displayName: string;
  status: string;
  expertProfile?: RunViewExpertProfile;
  latestSnapshot?: RunViewTeamMemberSnapshot;
  snapshots: RunViewTeamMemberSnapshot[];
  previewItems: RunViewTeamMemberPreviewItem[];
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

export interface RunViewQualityHighlight {
  label: string;
  status: "pass" | "warning" | "fail";
  detail: string;
}

export type RunViewEvidenceItem =
  | {
      id: string;
      source: "output";
      title: string;
      kind: string;
      summary: string;
      preview: WorkspaceResultPreview;
    }
  | {
      id: string;
      source: "node";
      title: string;
      kind: string;
      summary: string;
      nodeId: string;
      nodeState: ExecutionNodeState;
    };

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
  resultPreviews: WorkspaceResultPreview[];
  reviewItems: WorkspacePrismReviewItem[];
  evidenceItems: RunViewEvidenceItem[];
  pendingReviewCount: number;
  prismReviewCount?: number;
  sandboxReviewCount?: number;
  sandboxCount: number;
  hasPrismChanges: boolean;
  hasSandboxArtifacts?: boolean;
  failureCategory?: RunFailureCategory | null;
  failureMessage?: string | null;
  commitState: ExecutionCommitState | null;
  team?: RunViewTeam | null;
  qualityHighlights: RunViewQualityHighlight[];
  actions: RunPrimaryAction[];
}

type TaskReportProjection = Record<string, unknown> & {
  errors?: Array<Record<string, unknown>>;
  review_items?: unknown[];
};

const RUN_FAILURE_FALLBACK = "运行问题已记录";
const CITATION_SOURCE_AUDIT_SCHEMA =
  "wenjin.quality.citation_source_audit_finding.v1";
const MAX_CITATION_SOURCE_AUDIT_ITEMS = 8;

const TEAM_KERNEL_PROGRESS_ORDER = [
  "team_prepare",
  "team_recruit",
  "team_dispatch",
  "team_quality_gate",
  "team_finish",
] as const;

export function isTerminalRunStatus(status: RunViewStatus | string): boolean {
  return ["completed", "failed_partial", "failed", "cancelled"].includes(status);
}

export function runViewFromExecution(record: ExecutionRecord): RunView {
  const taskReport = taskReportFromResult(record.result);
  const reviewItems = readReviewItems(record);
  const outputResultPreviews = buildWorkspaceResultPreviewsFromOutputs(
    taskReport?.outputs,
  );
  const reviewResultPreviews =
    buildWorkspaceResultPreviewsFromReviewItems(reviewItems);
  const resultPreviews = [...outputResultPreviews, ...reviewResultPreviews];
  const evidenceItems = buildEvidenceItems(record, resultPreviews);
  const pendingReviewCount = outputResultPreviews.length + reviewItems.length;
  const sandboxCount = countSandboxEvidenceItems(evidenceItems);
  const tokenUsage =
    tokenUsageFromUnknown(taskReport?.token_usage) ??
    tokenUsageFromNodes(record.node_states);
  const prismReviewCount = countPrismReviewItems(reviewItems);
  const sandboxReviewCount = countSandboxReviewItems(reviewItems);
  const status = normalizeExecutionStatus(record.status);
  const failedNodeCount = countNodesByStatus(record, "failed");
  const progressItems = buildRunProgressItems(record);
  const completedNodeCount = progressItems.length
    ? countProgressItemsByStatus(progressItems, "completed")
    : countNodesByStatus(record, "completed");
  const nodeCount = progressItems.length
    ? progressItems.length
    : (record.graph_structure?.nodes.length ??
      Object.keys(record.node_states ?? {}).length);
  const rawFailureMessage = firstStringValue(
    record.last_error,
    record.error,
    taskReport?.errors?.[0]?.error,
  );
  const failureMessage = safeFailureMessage(
    record.last_error,
    record.error,
    taskReport?.errors?.[0]?.error,
  );
  const failureCategory =
    failureCategoryFromRecord(record, failedNodeCount, rawFailureMessage);
  const team = teamViewFromExecution(record);
  const qualityHighlights = qualityHighlightsFromRuntimeState(record.runtime_state);

  return {
    id: record.id,
    workspaceId: record.workspace_id ?? "",
    capabilityId: record.feature_id ?? stringValue(taskReport?.capability_id),
    title: runTitleFromExecution(record, taskReport),
    status,
    summary: safeRunSummary(
      status,
      record.result_summary,
      taskReport?.narrative,
      record.message,
      rawFailureMessage,
    ),
    startedAt: record.started_at ?? record.created_at,
    completedAt: record.completed_at ?? null,
    durationLabel: formatDuration(record.started_at ?? record.created_at, record.completed_at),
    progress: typeof record.progress === "number" ? record.progress : null,
    nodeCount,
    completedNodeCount,
    failedNodeCount,
    tokenUsage,
    resultPreviews,
    reviewItems,
    evidenceItems,
    pendingReviewCount,
    primarySurface:
      prismReviewCount > 0 ? "prism" : sandboxReviewCount > 0 ? "sandbox" : "rooms",
    prismReviewCount,
    sandboxReviewCount,
    sandboxCount,
    hasPrismChanges: prismReviewCount > 0,
    hasSandboxArtifacts: sandboxReviewCount > 0 || sandboxCount > 0,
    failureCategory,
    failureMessage,
    commitState: readCommitStateFromResult(record.result),
    team,
    qualityHighlights,
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
  if (record.graph_structure?.mode === "team_kernel") {
    return buildTeamKernelProgressItems(record, nodes);
  }
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
  const failureMessage = safeFailureMessage(record.failure_message);
  const failureCategory =
    record.failure_category ??
    (status === "failed" || status === "failed_partial" ? "unknown" : null);

  return {
    id: record.id,
    workspaceId: record.workspace_id ?? workspaceId,
    capabilityId: record.capability_id ?? null,
    title: humanizeCapabilityName(record.capability_name || record.capability_id) ?? "Execution",
    status,
    summary: safeRunSummary(status, record.summary),
    startedAt: record.started_at,
    completedAt: record.completed_at ?? null,
    durationLabel: formatDuration(record.started_at, record.completed_at ?? null),
    progress: typeof record.progress === "number" ? record.progress : null,
    tokenUsage: record.token_usage ?? null,
    resultPreviews: [],
    reviewItems: [],
    evidenceItems: [],
    pendingReviewCount: prismReviewCount + sandboxReviewCount,
    primarySurface:
      record.primary_surface ??
      (prismReviewCount > 0 || record.has_prism_changes
        ? "prism"
        : sandboxReviewCount > 0
          ? "sandbox"
          : "rooms"),
    prismReviewCount,
    sandboxReviewCount,
    sandboxCount: sandboxReviewCount,
    hasPrismChanges: Boolean(record.has_prism_changes || prismReviewCount > 0),
    hasSandboxArtifacts: sandboxReviewCount > 0,
    failureCategory,
    failureMessage,
    commitState: null,
    qualityHighlights: [],
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
  const reviewItems = coerceReviewItems(data.review_items);
  const outputResultPreviews = buildWorkspaceResultPreviewsFromOutputs(data.outputs);
  const reviewResultPreviews =
    buildWorkspaceResultPreviewsFromReviewItems(reviewItems);
  const resultPreviews = [...outputResultPreviews, ...reviewResultPreviews];
  const evidenceItems = buildOutputEvidenceItems(resultPreviews);
  const pendingReviewCount = outputResultPreviews.length + reviewItems.length;
  const prismReviewCount = countPrismReviewItems(reviewItems);
  const sandboxReviewCount = countSandboxReviewItems(reviewItems);
  const rawFailureMessage = firstStringValue(data.errors?.[0]?.message);
  const failureMessage = safeFailureMessage(data.errors?.[0]?.message);
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
    summary: safeRunSummary(status, data.narrative, rawFailureMessage),
    completedAt: null,
    durationLabel:
      typeof data.duration_seconds === "number"
        ? formatSeconds(data.duration_seconds)
        : null,
    tokenUsage: tokenUsageFromUnknown(data.token_usage),
    resultPreviews,
    reviewItems,
    evidenceItems,
    pendingReviewCount,
    primarySurface:
      prismReviewCount > 0 ? "prism" : sandboxReviewCount > 0 ? "sandbox" : "rooms",
    prismReviewCount,
    sandboxReviewCount,
    sandboxCount: sandboxReviewCount,
    hasPrismChanges: prismReviewCount > 0,
    hasSandboxArtifacts: sandboxReviewCount > 0,
    failureCategory,
    failureMessage,
    commitState: readCommitStateFromResult(data),
    qualityHighlights: [],
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
    summary: safeRunSummary(live.status, live.summary, historical.summary),
    startedAt: live.startedAt ?? historical.startedAt,
    completedAt: live.completedAt ?? historical.completedAt,
    durationLabel: live.durationLabel ?? historical.durationLabel,
    tokenUsage: live.tokenUsage ?? historical.tokenUsage,
    resultPreviews: live.resultPreviews.length
      ? live.resultPreviews
      : historical.resultPreviews,
    reviewItems: live.reviewItems.length ? live.reviewItems : historical.reviewItems,
    evidenceItems: live.evidenceItems.length
      ? live.evidenceItems
      : historical.evidenceItems,
    pendingReviewCount: Math.max(
      live.pendingReviewCount,
      historical.pendingReviewCount,
    ),
    primarySurface: live.primarySurface ?? historical.primarySurface,
    prismReviewCount: Math.max(
      live.prismReviewCount ?? 0,
      historical.prismReviewCount ?? 0,
    ),
    sandboxReviewCount: Math.max(
      live.sandboxReviewCount ?? 0,
      historical.sandboxReviewCount ?? 0,
    ),
    sandboxCount: Math.max(live.sandboxCount, historical.sandboxCount),
    hasPrismChanges: live.hasPrismChanges || historical.hasPrismChanges,
    hasSandboxArtifacts: Boolean(live.hasSandboxArtifacts || historical.hasSandboxArtifacts),
    failureCategory: live.failureCategory ?? historical.failureCategory,
    failureMessage: safeFailureMessage(live.failureMessage, historical.failureMessage),
    commitState: live.commitState ?? historical.commitState,
    team: live.team ?? historical.team,
    qualityHighlights: live.qualityHighlights.length
      ? live.qualityHighlights
      : historical.qualityHighlights,
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

export function readReviewItems(
  record: ExecutionRecord | null,
): WorkspacePrismReviewItem[] {
  if (!record) {
    return [];
  }
  if (record.review_items?.length) {
    return coerceReviewItems(record.review_items);
  }
  return coerceReviewItems(reviewItemsFromTaskReport(taskReportFromResult(record.result)));
}

function coerceReviewItems(value: unknown): WorkspacePrismReviewItem[] {
  return arrayValue(value)
    .filter((item) => item && typeof item === "object" && !Array.isArray(item))
    .map((item) => item as WorkspacePrismReviewItem);
}

export function buildEvidenceItems(
  record: ExecutionRecord | null,
  previews: WorkspaceResultPreview[],
): RunViewEvidenceItem[] {
  if (!record) {
    return [];
  }
  const outputItems = buildOutputEvidenceItems(previews);
  const graphNodes = record.graph_structure?.nodes ?? [];
  const nodeById = new Map(graphNodes.map((node) => [node.id, node]));
  const nodeItems: RunViewEvidenceItem[] = Object.entries(record.node_states ?? {})
    .filter(([, state]) =>
      Boolean(
        state.output ||
          state.output_preview ||
          state.tool_calls?.length ||
          buildHarnessEvidenceSummary(state)?.length,
      ),
    )
    .map(([nodeId, state]) => {
      const node = nodeById.get(nodeId);
      const output = state.output ?? {};
      const title = node?.label ?? node?.task ?? nodeId;
      const harnessEvidence = buildHarnessEvidenceSummary(state);
      const sandbox = harnessEvidence ?? buildSandboxSummary(state);
      const productSummary = buildProductSafeOutputSummary(state, output);
      return {
        id: `node:${nodeId}`,
        source: "node",
        title,
        kind: sandbox ? "sandbox" : node?.type ?? "node",
        summary:
          sandbox?.join(" · ") ??
          safeRuntimeText(state.output_preview) ??
          productSummary,
        nodeId,
        nodeState: state,
      };
    });
  const citationAuditItems = buildCitationSourceAuditEvidenceItems(record);
  return [...outputItems, ...citationAuditItems, ...nodeItems];
}

function buildOutputEvidenceItems(
  previews: WorkspaceResultPreview[],
): RunViewEvidenceItem[] {
  return previews.map((preview) => ({
    id: preview.id,
    source: "output",
    title: preview.title,
    kind: preview.kind,
    summary: [preview.subtitle, preview.previewText, ...preview.metadataLines]
      .filter(Boolean)
      .join(" · "),
    preview,
  }));
}

function buildHarnessEvidenceSummary(state: ExecutionNodeState): string[] | null {
  const harness = objectValue(objectValue(state.node_metadata)?.harness);
  const reproducibility = objectValue(harness?.reproducibility_summary);
  if (!reproducibility) {
    return null;
  }
  const scripts = safeWorkspacePathBasenames(reproducibility.script_paths, [
    "/workspace/scripts/",
  ]);
  const datasets = safeWorkspacePathBasenames(reproducibility.dataset_paths, [
    "/workspace/datasets/",
  ]);
  const artifacts = safeWorkspacePathBasenames(reproducibility.artifact_paths, [
    "/workspace/outputs/",
    "/workspace/reports/",
  ]);
  const nextActions = stringArrayValue(reproducibility.next_actions).slice(0, 2);
  const lines = [
    scripts.length ? `脚本：${formatShortList(scripts)}` : null,
    datasets.length ? `数据：${formatShortList(datasets)}` : null,
    artifacts.length ? `产物：${formatShortList(artifacts)}` : null,
    nextActions.length ? `后续：${formatShortList(nextActions)}` : null,
  ].filter((line): line is string => Boolean(line));
  return lines.length ? lines : null;
}

function buildCitationSourceAuditEvidenceItems(
  record: ExecutionRecord,
): RunViewEvidenceItem[] {
  const gates = qualityGateObjectsFromRuntimeState(record.runtime_state);
  const items: RunViewEvidenceItem[] = [];
  for (const gate of gates) {
    const gateId = stringValue(gate.gate_id) ?? stringValue(gate.id) ?? "citation_source_audit";
    const findings = arrayValue(gate.findings);
    for (const findingValue of findings) {
      const finding = objectValue(findingValue);
      const auditFindings = arrayValue(finding?.citation_source_audit);
      for (const auditValue of auditFindings) {
        const audit = objectValue(auditValue);
        if (!audit || stringValue(audit.schema) !== CITATION_SOURCE_AUDIT_SCHEMA) {
          continue;
        }
        const summary = citationSourceAuditSummary(audit);
        if (!summary) {
          continue;
        }
        const severity = stringValue(audit.severity) ?? stringValue(gate.severity);
        const status = stringValue(gate.status) ?? "warning";
        const title = `引文与来源风险 · ${qualityGateEvidenceDisplayName(gateId)}`;
        const nodeState: ExecutionNodeState = {
          status,
          node_type: "quality_gate",
          label: title,
          output_preview: summary,
          node_metadata: {
            quality_gate: {
              gate_id: gateId,
              severity,
              status,
              finding_count: auditFindings.length,
            },
          },
        };
        items.push({
          id: `quality-gate:${gateId}:citation-source-audit:${items.length + 1}`,
          source: "node",
          title,
          kind: "citation",
          summary,
          nodeId: `quality-gate:${gateId}`,
          nodeState,
        });
        if (items.length >= MAX_CITATION_SOURCE_AUDIT_ITEMS) {
          return items;
        }
      }
    }
  }
  return items;
}

function qualityGateObjectsFromRuntimeState(
  runtimeState: Record<string, unknown> | null | undefined,
): Record<string, unknown>[] {
  const direct = arrayValue(runtimeState?.quality_gates);
  const nested = arrayValue(objectValue(runtimeState?.team)?.quality_gates);
  return [...direct, ...nested]
    .map((value) => objectValue(value))
    .filter((value): value is Record<string, unknown> => Boolean(value));
}

function citationSourceAuditSummary(audit: Record<string, unknown>): string | null {
  const refs = [
    stringValue(audit.citation_key),
    stringValue(audit.source_id),
    ...stringArrayValue(audit.unknown_refs).map((ref) => `未确认 ${ref}`),
  ].filter((value): value is string => Boolean(value));
  const risk = riskLabel(stringValue(audit.risk));
  const severity = severityLabel(stringValue(audit.severity));
  const message = stringValue(audit.message);
  const action = citationAuditActionLabel(stringValue(audit.suggested_action));
  const claim = stringValue(audit.claim);
  const lines = [
    refs.length ? `对象：${formatShortList(refs)}` : null,
    risk || severity ? `风险：${[risk, severity].filter(Boolean).join(" / ")}` : null,
    message ? `问题：${truncate(message, 96)}` : null,
    action ? `建议：${action}` : null,
    claim ? `论断：${truncate(claim, 120)}` : null,
  ].filter((line): line is string => Boolean(line));
  return lines.length ? lines.join(" · ") : null;
}

function qualityGateEvidenceDisplayName(gateId: string): string {
  const normalized = gateId.toLowerCase();
  if (normalized.includes("fabricated") || normalized.includes("citation")) {
    return "引用真实性检查";
  }
  if (normalized.includes("source")) {
    return "来源完整性检查";
  }
  return gateId
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function riskLabel(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const normalized = value.toLowerCase();
  if (normalized.includes("fabricated")) return "疑似编造";
  if (normalized.includes("missing")) return "缺少来源";
  if (normalized.includes("unsupported")) return "缺少证据支撑";
  return value;
}

function severityLabel(value: string | null): string | null {
  if (value === "high") return "高";
  if (value === "medium") return "中";
  if (value === "low") return "低";
  return value;
}

function citationAuditActionLabel(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const normalized = value.toLowerCase();
  if (normalized.includes("replace") || normalized.includes("remove")) {
    return "替换或删除";
  }
  if (normalized.includes("attach") || normalized.includes("source")) {
    return "补充可信来源";
  }
  if (normalized.includes("review")) {
    return "人工复核";
  }
  return value.replace(/[_-]+/g, " ");
}

export function buildSandboxSummary(
  state: ExecutionNodeState | null | undefined,
): string[] | null {
  if (!state) {
    return null;
  }
  const output = state.output;
  const tool = state.tool_calls?.find((call) =>
    stringValue(call.name)?.includes("sandbox"),
  );
  const hasSandboxOutput =
    output &&
    (stringValue(output.engine)?.includes("sandbox") ||
      stringValue(output.operation) === "smoke_check" ||
      output.exit_code !== undefined ||
      stringValue(output.docker_image));
  if (!tool && !hasSandboxOutput) {
    return null;
  }
  const outputRefCount =
    recoverableOutputRefCount(output?.output_refs, output?.output_ref) +
    recoverableOutputRefCount(tool?.output_refs, tool?.output_ref);
  const hasBoundedOutput =
    Boolean(stringValue(output?.stdout)) ||
    Boolean(stringValue(tool?.stdout)) ||
    Boolean(stringValue(output?.stderr)) ||
    Boolean(stringValue(tool?.stderr)) ||
    outputRefCount > 0;
  const lines = [
    `操作：${stringValue(output?.operation) ?? stringValue(tool?.name) ?? "实验环境"}`,
    `状态：${stringValue(output?.status) ?? stringValue(tool?.status) ?? state.status ?? "unknown"}`,
    output?.exit_code !== undefined || tool?.exit_code !== undefined
      ? `Exit code：${String(output?.exit_code ?? tool?.exit_code)}`
      : null,
    stringValue(output?.docker_image) || stringValue(tool?.docker_image)
      ? `镜像：${stringValue(output?.docker_image) ?? stringValue(tool?.docker_image)}`
      : null,
    hasBoundedOutput
      ? `输出：${outputRefCount > 0 ? `${outputRefCount} 个可恢复引用` : "已生成运行结果"}`
      : null,
  ].filter((line): line is string => Boolean(line));
  return lines.length > 0 ? lines : null;
}

function buildProductSafeOutputSummary(
  state: ExecutionNodeState,
  output: Record<string, unknown>,
): string {
  const explicitSummary =
    safeRuntimeText(output.summary) ??
    safeRuntimeText(output.result_summary) ??
    safeRuntimeText(output.narrative) ??
    safeRuntimeText(output.preview) ??
    safeRuntimeText(output.message);
  const operation = safeRuntimeText(output.operation) ?? safeRuntimeText(output.action);
  const status = stringValue(output.status) ?? state.status ?? null;
  const outputRefCount =
    recoverableOutputRefCount(output.output_refs, output.output_ref) +
    recoverableOutputRefCount(
      ...(state.tool_calls ?? []).flatMap((call) => [call.output_refs, call.output_ref]),
    );
  const resultFallback =
    outputRefCount > 0
      ? `输出：${outputRefCount} 个可恢复引用`
      : hasProductOutputSignal(output)
        ? "已生成运行结果"
        : "运行记录已更新";
  const lines = [
    explicitSummary,
    operation ? `操作：${operation}` : null,
    status ? `状态：${statusLabel(status)}` : null,
    resultFallback,
  ].filter((line): line is string => Boolean(line));
  return lines.join(" · ");
}

function hasProductOutputSignal(output: Record<string, unknown>): boolean {
  return Boolean(
    safeRuntimeText(output.content) ||
      safeRuntimeText(output.value) ||
      safeRuntimeText(output.result) ||
      safeRuntimeText(output.text) ||
      safeRuntimeText(output.title) ||
      safeRuntimeText(output.description),
  );
}

function countSandboxEvidenceItems(items: RunViewEvidenceItem[]): number {
  return items.filter(
    (item) => item.kind === "sandbox" || item.summary.includes("sandbox"),
  ).length;
}

function safeWorkspacePathBasenames(value: unknown, allowedPrefixes: string[]): string[] {
  return stringArrayValue(value)
    .filter((path) => isSafeEvidencePath(path, allowedPrefixes))
    .slice(0, 4)
    .map((path) => path.split("/").filter(Boolean).at(-1) ?? path);
}

function isSafeEvidencePath(path: string, allowedPrefixes: string[]): boolean {
  if (!allowedPrefixes.some((prefix) => path.startsWith(prefix))) {
    return false;
  }
  if (path.startsWith("/workspace/outputs/harness/")) {
    return false;
  }
  return !/(^|\/)(\.wenjin|\.env(?:\..*)?|[^/]+\.(?:pem|key))($|\/)/i.test(path);
}

function formatShortList(items: string[]): string {
  if (items.length <= 3) {
    return items.join("、");
  }
  return `${items.slice(0, 3).join("、")} 等 ${items.length} 项`;
}

function truncate(value: string, max: number): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= max) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(0, max - 3))}...`;
}

function statusLabel(status: string): string {
  if (status === "launching") return "启动中";
  if (status === "queued" || status === "pending") return "排队中";
  if (status === "running" || status === "cancelling") return "运行中";
  if (status === "completed") return "已完成";
  if (status === "failed_partial") return "部分完成";
  if (status === "failed") return "失败";
  if (status === "cancelled") return "已取消";
  return status || "未知";
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
    if (nodeType !== "agent_invocation" || metadata?.team !== true) {
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
    const harness = objectValue(metadata?.harness);
    const snapshots = expertSnapshotsFromHarness(harness);
    const previewItems = expertPreviewItemsFromHarness(harness, id);
    const latestSnapshot = snapshots.at(-1);
    const expertProfile = expertProfileFromMetadata(metadata, latestSnapshot);
    members.push({
      id,
      templateId,
      displayName,
      status: stringValue(node.status) ?? "pending",
      ...(expertProfile ? { expertProfile } : {}),
      ...(latestSnapshot ? { latestSnapshot } : {}),
      snapshots,
      previewItems,
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

function expertProfileFromMetadata(
  metadata: Record<string, unknown> | null,
  latestSnapshot?: RunViewTeamMemberSnapshot,
): RunViewExpertProfile | undefined {
  const raw = objectValue(metadata?.expert_profile);
  const publicName = stringValue(raw?.public_name) ?? stringValue(metadata?.display_name);
  const roleTitle = stringValue(raw?.role_title) ?? stringValue(metadata?.assigned_role);
  if (!publicName || !roleTitle) return undefined;
  const tone = raw?.tone === "witty_professional" ? "witty_professional" : "professional";
  const avatarLabel =
    stringValue(raw?.avatar_label) ??
    publicName.trim().slice(0, 1) ??
    roleTitle.trim().slice(0, 1);
  return {
    publicName,
    roleTitle,
    avatarLabel,
    tone,
    ...(stringValue(raw?.short_name) ? { shortName: stringValue(raw?.short_name)! } : {}),
    ...(stringValue(raw?.tagline) ? { tagline: stringValue(raw?.tagline)! } : {}),
    ...(latestSnapshot?.headline ? { statusPhrase: latestSnapshot.headline } : {}),
  };
}

function expertSnapshotsFromHarness(
  harness: Record<string, unknown> | null,
): RunViewTeamMemberSnapshot[] {
  const snapshots = arrayValue(harness?.expert_snapshots)
    .map((item) => expertSnapshotFromUnknown(item))
    .filter((item): item is RunViewTeamMemberSnapshot => Boolean(item));
  return snapshots
    .sort((left, right) => left.createdAt.localeCompare(right.createdAt))
    .slice(-5);
}

function expertSnapshotFromUnknown(value: unknown): RunViewTeamMemberSnapshot | null {
  const raw = objectValue(value);
  if (!raw) return null;
  const id = stringValue(raw.snapshot_id) ?? stringValue(raw.id);
  const headline = stringValue(raw.headline);
  const body = stringValue(raw.body);
  const stage = objectValue(raw.stage);
  if (!id || !headline || !body) return null;
  const status = normalizeExpertSnapshotStatus(raw.status);
  const updateKind = normalizeExpertUpdateKind(raw.update_kind);
  return {
    id,
    status,
    updateKind,
    stageLabel: stringValue(stage?.label) ?? "正在处理",
    headline,
    body,
    chips: arrayValue(raw.chips)
      .map((item) => {
        const chip = objectValue(item);
        const label = stringValue(chip?.label);
        if (!label) return null;
        return {
          label,
          ...(stringValue(chip?.value) ? { value: stringValue(chip?.value)! } : {}),
          ...(stringValue(chip?.tone) ? { tone: stringValue(chip?.tone)! } : {}),
        };
      })
      .filter((item): item is { label: string; value?: string; tone?: string } => Boolean(item)),
    evidenceRefs: arrayValue(raw.evidence_refs)
      .map((item) => {
        const ref = objectValue(item);
        const label = stringValue(ref?.label);
        const type = stringValue(ref?.ref_type);
        if (!label || !type) return null;
        return {
          label,
          type,
          ...(stringValue(ref?.ref_id) ? { refId: stringValue(ref?.ref_id)! } : {}),
          ...(stringValue(ref?.path) ? { path: stringValue(ref?.path)! } : {}),
          ...(typeof ref?.count === "number" ? { count: ref.count } : {}),
        };
      })
      .filter((item): item is RunViewTeamMemberSnapshot["evidenceRefs"][number] => Boolean(item)),
    outputRefs: arrayValue(raw.output_refs)
      .map((item) => {
        const ref = objectValue(item);
        const label = stringValue(ref?.label);
        const kind = stringValue(ref?.kind);
        if (!label || !kind) return null;
        return {
          label,
          kind,
          ...(stringValue(ref?.ref_id) ? { refId: stringValue(ref?.ref_id)! } : {}),
          ...(stringValue(ref?.preview_item_id) ? { previewItemId: stringValue(ref?.preview_item_id)! } : {}),
          ...(stringValue(ref?.path) ? { path: stringValue(ref?.path)! } : {}),
          ...(stringValue(ref?.status) ? { status: stringValue(ref?.status)! } : {}),
        };
      })
      .filter((item): item is RunViewTeamMemberSnapshot["outputRefs"][number] => Boolean(item)),
    ...(stringValue(raw.next_step) ? { nextStep: stringValue(raw.next_step)! } : {}),
    ...(raw.confidence === "low" || raw.confidence === "medium" || raw.confidence === "high"
      ? { confidence: raw.confidence }
      : {}),
    createdAt: stringValue(raw.created_at) ?? "",
  };
}

function expertPreviewItemsFromHarness(
  harness: Record<string, unknown> | null,
  ownerMemberId: string,
): RunViewTeamMemberPreviewItem[] {
  return arrayValue(harness?.expert_preview_items)
    .map((item) => {
      const raw = objectValue(item);
      const id = stringValue(raw?.preview_item_id) ?? stringValue(raw?.id);
      const title = stringValue(raw?.title);
      const kind = stringValue(raw?.kind);
      const summary = stringValue(raw?.summary);
      if (!id || !title || !kind || !summary) return null;
      return {
        id,
        ownerMemberId,
        title,
        kind,
        summary,
        status: normalizePreviewStatus(raw?.status),
        ...(stringValue(raw?.subtitle) ? { subtitle: stringValue(raw?.subtitle)! } : {}),
        ...(stringValue(raw?.preview_payload_ref) ? { payloadRef: stringValue(raw?.preview_payload_ref)! } : {}),
        sourceRefs: arrayValue(raw?.source_refs)
          .map((item) => {
            const ref = objectValue(item);
            const label = stringValue(ref?.label);
            const type = stringValue(ref?.ref_type);
            if (!label || !type) return null;
            return {
              label,
              type,
              ...(stringValue(ref?.ref_id) ? { refId: stringValue(ref?.ref_id)! } : {}),
              ...(stringValue(ref?.path) ? { path: stringValue(ref?.path)! } : {}),
            };
          })
          .filter((item): item is RunViewTeamMemberPreviewItem["sourceRefs"][number] => Boolean(item)),
        createdAt: stringValue(raw?.created_at) ?? "",
      };
    })
    .filter((item): item is RunViewTeamMemberPreviewItem => Boolean(item))
    .sort((left, right) => left.createdAt.localeCompare(right.createdAt))
    .slice(-20);
}

function normalizeExpertSnapshotStatus(value: unknown): RunViewTeamMemberSnapshot["status"] {
  if (
    value === "queued" ||
    value === "running" ||
    value === "blocked" ||
    value === "completed" ||
    value === "failed"
  ) {
    return value;
  }
  return "running";
}

function normalizeExpertUpdateKind(value: unknown): RunViewTeamMemberSnapshot["updateKind"] {
  if (
    value === "progress" ||
    value === "finding" ||
    value === "risk" ||
    value === "decision" ||
    value === "output" ||
    value === "question"
  ) {
    return value;
  }
  return "progress";
}

function normalizePreviewStatus(value: unknown): RunViewTeamMemberPreviewItem["status"] {
  if (value === "draft" || value === "ready" || value === "saved") return value;
  return "draft";
}

function teamQualityGatesFromRuntimeState(
  runtimeState: Record<string, unknown> | null | undefined,
): RunViewQualityGate[] {
  const direct = arrayValue(runtimeState?.quality_gates);
  const nested = arrayValue(objectValue(runtimeState?.team)?.quality_gates);
  const orderedIds: string[] = [];
  const byId = new Map<string, RunViewQualityGate>();
  for (const rawGate of [...direct, ...nested]) {
    const gate = objectValue(rawGate);
    if (!gate) continue;
    const id = stringValue(gate.gate_id) ?? stringValue(gate.id);
    if (!id) continue;
    const severity = normalizeQualityGateSeverity(gate.severity);
    if (!byId.has(id)) orderedIds.push(id);
    byId.set(id, {
      id,
      status: normalizeQualityGateStatus(gate.status),
      ...(severity ? { severity } : {}),
      nextAction: stringValue(gate.next_action) ?? stringValue(gate.nextAction),
    });
  }
  return orderedIds
    .map((id) => byId.get(id))
    .filter((gate): gate is RunViewQualityGate => Boolean(gate));
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

function qualityHighlightsFromRuntimeState(
  runtimeState: Record<string, unknown> | null | undefined,
): RunViewQualityHighlight[] {
  const gates = teamQualityGatesFromRuntimeState(runtimeState);
  const rawGates = [
    ...arrayValue(runtimeState?.quality_gates),
    ...arrayValue(objectValue(runtimeState?.team)?.quality_gates),
  ];
  const rawById = new Map<string, Record<string, unknown>>();
  for (const rawGate of rawGates) {
    const gate = objectValue(rawGate);
    if (!gate) continue;
    const id = stringValue(gate.gate_id) ?? stringValue(gate.id);
    if (id) rawById.set(id, gate);
  }

  const highlights: RunViewQualityHighlight[] = [];
  for (const gate of gates) {
    const normalized = normalizeTechnicalName(gate.id);
    const rawGate = rawById.get(gate.id) ?? {};
    const evidence = objectValue(rawGate.evidence) ?? objectValue(rawGate.result) ?? {};
    const highlight = qualityHighlightFromGate(gate, normalized, evidence);
    if (highlight) highlights.push(highlight);
  }
  return highlights.slice(0, 6);
}

function qualityHighlightFromGate(
  gate: RunViewQualityGate,
  normalizedId: string,
  evidence: Record<string, unknown>,
): RunViewQualityHighlight | null {
  if (normalizedId.includes("citation_strength")) {
    const strongCount = numberValue(evidence.strong_count);
    return {
      label: "引用支撑",
      status: gate.status,
      detail: strongCount > 0 ? `${strongCount} 条强支撑` : qualityDetailForStatus(gate.status),
    };
  }
  if (normalizedId.includes("experiment_interpretation")) {
    return {
      label: "实验解释",
      status: gate.status,
      detail: gate.status === "pass" ? "指标、限制与产物已对齐" : qualityDetailForStatus(gate.status),
    };
  }
  if (normalizedId.includes("statistical_robustness")) {
    return {
      label: "统计稳健",
      status: gate.status,
      detail: gate.status === "pass" ? "方法、样本量与稳健性已检查" : qualityDetailForStatus(gate.status),
    };
  }
  if (normalizedId.includes("writing_semantic_preservation")) {
    const riskyCount = arrayValue(evidence.risky_items).length || numberValue(evidence.high_risk_count);
    return {
      label: "语义保持",
      status: gate.status,
      detail: riskyCount > 0 ? `${riskyCount} 处改写需要确认` : qualityDetailForStatus(gate.status),
    };
  }
  return null;
}

function qualityDetailForStatus(status: RunViewQualityHighlight["status"]): string {
  if (status === "pass") return "已检查";
  if (status === "fail") return "需要修订";
  return "需要确认";
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

function buildTeamKernelProgressItems(
  record: ExecutionRecord,
  nodes: ExecutionGraphNode[],
): RunProgressItem[] {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const teamNodes = TEAM_KERNEL_PROGRESS_ORDER
    .map((id) => nodeById.get(id))
    .filter((node): node is ExecutionGraphNode => Boolean(node));

  return teamNodes.map((node) => {
    const status = teamKernelProgressStatus(record, node.id);
    return {
      id: node.id,
      title: executionNodeDisplayName(node, null),
      phaseTitle: executionPhaseDisplayName(node.phase),
      status,
      detail: teamKernelProgressDetail(record, node.id, status),
      technicalName: node.id,
      startedAt: record.started_at ?? record.created_at,
      completedAt: isTerminalRunStatus(status) ? record.completed_at ?? null : null,
      toolCount: 0,
      hasInput: false,
      hasOutput: node.id === "team_finish" && Boolean(record.result),
    };
  });
}

function teamKernelProgressStatus(
  record: ExecutionRecord,
  nodeId: string,
): string {
  const runStatus = normalizeExecutionStatus(record.status);
  const terminal = isTerminalRunStatus(runStatus);
  const members = teamMembersFromNodeStates(record.node_states);
  const qualityGates = teamQualityGatesFromRuntimeState(record.runtime_state);
  const dispatchStatus = aggregateTeamMemberStatus(members.map((member) => member.status));

  if (nodeId === "team_prepare") {
    if (runStatus === "queued" || runStatus === "launching") return "pending";
    return terminal || members.length > 0 ? "completed" : "running";
  }

  if (nodeId === "team_recruit") {
    if (members.length > 0) return "completed";
    return terminal ? "failed" : runStatus === "queued" ? "pending" : "running";
  }

  if (nodeId === "team_dispatch") {
    return dispatchStatus;
  }

  if (nodeId === "team_quality_gate") {
    if (qualityGates.length > 0) {
      if (qualityGates.some((gate) => gate.status === "fail")) return "failed";
      if (qualityGates.some((gate) => gate.status === "warning")) return "failed_partial";
      return "completed";
    }
    if (dispatchStatus === "completed" && terminal) return "completed";
    if (dispatchStatus === "running") return "pending";
    return dispatchStatus === "failed" ? "failed" : "pending";
  }

  if (nodeId === "team_finish") {
    if (!terminal) {
      return dispatchStatus === "completed" ? "running" : "pending";
    }
    if (runStatus === "failed" && !record.result) return "failed";
    if (runStatus === "cancelled") return "cancelled";
    return record.result || record.result_summary || record.completed_at
      ? "completed"
      : runStatus;
  }

  return "pending";
}

function aggregateTeamMemberStatus(statuses: string[]): string {
  if (statuses.length === 0) return "pending";
  if (statuses.some((status) => status === "running" || status === "launching")) {
    return "running";
  }
  if (statuses.some((status) => status === "failed")) {
    return statuses.some((status) => status === "completed") ? "failed_partial" : "failed";
  }
  if (statuses.some((status) => status === "cancelled")) return "cancelled";
  if (statuses.every((status) => status === "completed")) return "completed";
  return "running";
}

function teamKernelProgressDetail(
  record: ExecutionRecord,
  nodeId: string,
  status: string,
): string | null {
  const members = teamMembersFromNodeStates(record.node_states);
  if (nodeId === "team_recruit" && members.length > 0) {
    return `${members.length} 个团队成员已就绪`;
  }
  if (nodeId === "team_dispatch" && members.length > 0) {
    const completed = members.filter((member) => member.status === "completed").length;
    const failed = members.filter((member) => member.status === "failed").length;
    if (failed > 0) return `${completed} 个成员完成，${failed} 个成员需要复核`;
    return `${completed}/${members.length} 个成员完成`;
  }
  if (nodeId === "team_quality_gate") {
    const gates = teamQualityGatesFromRuntimeState(record.runtime_state);
    if (gates.length > 0) {
      const warnings = gates.filter((gate) => gate.status === "warning").length;
      const failed = gates.filter((gate) => gate.status === "fail").length;
      if (failed > 0) return `${failed} 个质量检查未通过`;
      if (warnings > 0) return `${warnings} 个质量检查需要注意`;
      return `${gates.length} 个质量检查已通过`;
    }
  }
  if (nodeId === "team_finish" && status === "completed") {
    return "结果已进入待确认区";
  }
  return null;
}

function countProgressItemsByStatus(
  items: RunProgressItem[],
  status: string,
): number {
  return items.filter((item) => item.status === status).length;
}

function progressDetailFromNodeState(state: ExecutionNodeState | null): string | null {
  if (!state) return null;
  const error = safeRuntimeText(state.error, 120);
  if (error) return error;
  if (state.error) return "运行问题已记录";
  const harnessActivity = harnessActivityFromNodeState(state).label;
  if (harnessActivity) return harnessActivity;
  const thinking = safeRuntimeText(state.thinking, 140);
  if (thinking) return thinking;
  const outputPreview = safeRuntimeText(state.output_preview, 140);
  if (outputPreview) return outputPreview;
  return null;
}

function harnessActivityFromNodeState(
  state: ExecutionNodeState | null | undefined,
): { label: string | null; artifactCount: number } {
  const harness = objectValue(objectValue(state?.node_metadata)?.harness);
  if (!harness) return { label: null, artifactCount: 0 };
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
  const journalSummary = objectValue(harness.run_journal_summary);
  const journalLabel = stringValue(journalSummary?.summary);
  if (journalLabel) {
    const artifactCount = Number(journalSummary?.artifact_count ?? 0);
    return {
      label: trimForDisplay(journalLabel, 120),
      artifactCount: Number.isFinite(artifactCount) && artifactCount > 0 ? artifactCount : 0,
    };
  }
  const reproducibilityActivity = reproducibilityActivityFromHarnessSummary(
    objectValue(harness.reproducibility_summary),
    state?.status,
  );
  if (reproducibilityActivity.label) {
    return reproducibilityActivity;
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

function reproducibilityActivityFromHarnessSummary(
  summary: Record<string, unknown> | null,
  status?: string | null,
): { label: string | null; artifactCount: number } {
  if (!summary) return { label: null, artifactCount: 0 };
  const scriptCount = countSummaryItems(summary.script_paths);
  const datasetCount = countSummaryItems(summary.dataset_paths);
  const artifactCount = countSummaryItems(summary.artifact_paths);
  const nextActionCount = countSummaryItems(summary.next_actions);
  const pythonRuns = Number(summary.python_runs ?? 0);
  const hasRunEvidence =
    scriptCount > 0 ||
    datasetCount > 0 ||
    artifactCount > 0 ||
    (Number.isFinite(pythonRuns) && pythonRuns > 0);

  if (status === "running" && hasRunEvidence) {
    return { label: "正在运行可复现实验", artifactCount };
  }

  const parts = [
    scriptCount > 0 ? `${scriptCount} 个脚本` : null,
    datasetCount > 0 ? `${datasetCount} 个数据集` : null,
    artifactCount > 0 ? `${artifactCount} 个产物` : null,
  ].filter((part): part is string => Boolean(part));
  if (parts.length > 0) {
    return {
      label: `已完成可复现实验：${parts.join(" · ")}`,
      artifactCount,
    };
  }
  if (nextActionCount > 0) {
    return { label: "实验已完成，等待复核", artifactCount: 0 };
  }
  if (Number.isFinite(pythonRuns) && pythonRuns > 0) {
    return { label: "已完成可复现实验", artifactCount: 0 };
  }
  return { label: null, artifactCount: 0 };
}

function countSummaryItems(value: unknown): number {
  return arrayValue(value).filter((item) => stringValue(item)).length;
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
    [/critical|reviewer|critic|quality.*review|peer.*review/, "质量风险专家"],
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

function safeRunSummary(status: RunViewStatus, ...values: unknown[]): string {
  return userFacingRunSummary(firstSafeRuntimeText(values, 240) ?? statusSummary(status));
}

function safeFailureMessage(...values: unknown[]): string | null {
  const safe = firstSafeRuntimeText(values, 240);
  if (safe) {
    return userFacingRunSummary(safe);
  }
  return firstStringValue(...values) ? RUN_FAILURE_FALLBACK : null;
}

function firstSafeRuntimeText(values: unknown[], max: number): string | null {
  for (const value of values) {
    const text = safeRuntimeText(value, max);
    if (text) {
      return text;
    }
  }
  return null;
}

function userFacingRunSummary(value: string): string {
  return value
    .replace(/launch_feature/g, "研究任务")
    .replace(/DataService rooms?/g, "工作区资料")
    .replace(/DataService/g, "工作区资料")
    .replace(/Sandbox Python/g, "实验环境")
    .replace(/Sandbox/g, "实验环境")
    .replace(/quality gate/gi, "风险项")
    .replace(/质量门/g, "风险项")
    .replace(/审阅/g, "确认");
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

function firstStringValue(...values: unknown[]): string | null {
  for (const value of values) {
    const text = stringValue(value);
    if (text) {
      return text;
    }
  }
  return null;
}

function objectValue(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function numberValue(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return Math.max(0, value);
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
  }
  return 0;
}

function stringArrayValue(value: unknown): string[] {
  return arrayValue(value)
    .map((item) => stringValue(item))
    .filter((item): item is string => Boolean(item));
}
