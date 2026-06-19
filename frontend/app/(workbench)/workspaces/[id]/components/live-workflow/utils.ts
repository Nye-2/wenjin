import type { CSSProperties, Dispatch, SetStateAction } from "react";

import type {
  ExecutionNodeState,
  ExecutionRecord,
  WorkspacePrismReviewItem,
} from "@/lib/api/types";
import type { CommittedRoomLink } from "@/lib/execution-commit";
import type { RunViewStatus } from "@/lib/execution-run-view";
import { getWorkspaceResultKindMeta } from "@/lib/workspace-result-kind";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";
import { extractTaskReport } from "@/lib/workbench-result-editing";
import type { WorkbenchDraftEdit } from "@/stores/workbench-layout-store";

import type { EvidenceItem } from "./types";

const CITATION_SOURCE_AUDIT_SCHEMA =
  "wenjin.quality.citation_source_audit_finding.v1";
const MAX_CITATION_SOURCE_AUDIT_ITEMS = 8;

export const TERMINAL_STATUSES = new Set([
  "completed",
  "failed_partial",
  "failed",
  "cancelled",
]);

export function buildEvidenceItems(
  record: ExecutionRecord | null,
  previews: WorkspaceResultPreview[],
): EvidenceItem[] {
  if (!record) {
    return [];
  }
  const outputItems: EvidenceItem[] = previews.map((preview) => ({
    id: preview.id,
    source: "output",
    title: preview.title,
    kind: preview.kind,
    summary: [preview.subtitle, preview.previewText, ...preview.metadataLines]
      .filter(Boolean)
      .join(" · "),
    preview,
  }));
  const graphNodes = record.graph_structure?.nodes ?? [];
  const nodeById = new Map(graphNodes.map((node) => [node.id, node]));
  const nodeItems: EvidenceItem[] = Object.entries(record.node_states ?? {})
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
      return {
        id: `node:${nodeId}`,
        source: "node",
        title,
        kind: sandbox ? "sandbox" : node?.type ?? "node",
        summary:
          sandbox?.join(" · ") ??
          state.output_preview ??
          readString((output as Record<string, unknown>).summary) ??
          truncate(formatJsonPreview(output), 180),
        nodeId,
        nodeState: state,
      };
    });
  const citationAuditItems = buildCitationSourceAuditEvidenceItems(record);
  return [...outputItems, ...citationAuditItems, ...nodeItems];
}

function buildHarnessEvidenceSummary(state: ExecutionNodeState): string[] | null {
  const harness = readObject(readObject(state.node_metadata)?.harness);
  const reproducibility = readObject(harness?.reproducibility_summary);
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

function buildCitationSourceAuditEvidenceItems(record: ExecutionRecord): EvidenceItem[] {
  const gates = qualityGateObjectsFromRuntimeState(record.runtime_state);
  const items: EvidenceItem[] = [];
  for (const gate of gates) {
    const gateId = readString(gate.gate_id) ?? readString(gate.id) ?? "citation_source_audit";
    const findings = unknownArrayValue(gate.findings);
    for (const findingValue of findings) {
      const finding = readObject(findingValue);
      const auditFindings = unknownArrayValue(finding?.citation_source_audit);
      for (const auditValue of auditFindings) {
        const audit = readObject(auditValue);
        if (!audit || readString(audit.schema) !== CITATION_SOURCE_AUDIT_SCHEMA) {
          continue;
        }
        const summary = citationSourceAuditSummary(audit);
        if (!summary) {
          continue;
        }
        const severity = readString(audit.severity) ?? readString(gate.severity);
        const status = readString(gate.status) ?? "warning";
        const title = `引文与来源风险 · ${qualityGateDisplayName(gateId)}`;
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
  const direct = unknownArrayValue(runtimeState?.quality_gates);
  const nested = unknownArrayValue(readObject(runtimeState?.team)?.quality_gates);
  return [...direct, ...nested]
    .map((value) => readObject(value))
    .filter((value): value is Record<string, unknown> => Boolean(value));
}

function citationSourceAuditSummary(audit: Record<string, unknown>): string | null {
  const refs = [
    readString(audit.citation_key),
    readString(audit.source_id),
    ...stringArrayValue(audit.unknown_refs).map((ref) => `未确认 ${ref}`),
  ].filter((value): value is string => Boolean(value));
  const risk = riskLabel(readString(audit.risk));
  const severity = severityLabel(readString(audit.severity));
  const message = readString(audit.message);
  const action = citationAuditActionLabel(readString(audit.suggested_action));
  const claim = readString(audit.claim);
  const lines = [
    refs.length ? `对象：${formatShortList(refs)}` : null,
    risk || severity ? `风险：${[risk, severity].filter(Boolean).join(" / ")}` : null,
    message ? `问题：${truncate(message, 96)}` : null,
    action ? `建议：${action}` : null,
    claim ? `论断：${truncate(claim, 120)}` : null,
  ].filter((line): line is string => Boolean(line));
  return lines.length ? lines.join(" · ") : null;
}

function qualityGateDisplayName(gateId: string): string {
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

export function readReviewItems(record: ExecutionRecord | null): WorkspacePrismReviewItem[] {
  if (!record) {
    return [];
  }
  if (record.review_items?.length) {
    return record.review_items;
  }
  const report = extractTaskReport(record.result);
  const items = report?.review_items;
  if (!Array.isArray(items)) {
    return [];
  }
  return items
    .filter((item) => item && typeof item === "object" && !Array.isArray(item))
    .map((item) => item as WorkspacePrismReviewItem);
}

export function buildSandboxSummary(state: ExecutionNodeState | null | undefined): string[] | null {
  if (!state) {
    return null;
  }
  const output = state.output;
  const tool = state.tool_calls?.find((call) =>
    readString(call.name)?.includes("sandbox"),
  );
  const hasSandboxOutput =
    output &&
    (readString(output.engine)?.includes("sandbox") ||
      readString(output.operation) === "smoke_check" ||
      output.exit_code !== undefined ||
      readString(output.docker_image));
  if (!tool && !hasSandboxOutput) {
    return null;
  }
  const outputRefCount =
    unknownArrayValue(output?.output_refs).length +
    unknownArrayValue(tool?.output_refs).length;
  const hasBoundedOutput =
    Boolean(readString(output?.stdout)) ||
    Boolean(readString(tool?.stdout)) ||
    Boolean(readString(output?.stderr)) ||
    Boolean(readString(tool?.stderr)) ||
    outputRefCount > 0;
  const lines = [
    `操作：${readString(output?.operation) ?? readString(tool?.name) ?? "实验环境"}`,
    `状态：${readString(output?.status) ?? readString(tool?.status) ?? state.status ?? "unknown"}`,
    output?.exit_code !== undefined || tool?.exit_code !== undefined
      ? `Exit code：${String(output?.exit_code ?? tool?.exit_code)}`
      : null,
    readString(output?.docker_image) || readString(tool?.docker_image)
      ? `镜像：${readString(output?.docker_image) ?? readString(tool?.docker_image)}`
      : null,
    hasBoundedOutput
      ? `输出：${outputRefCount > 0 ? `${outputRefCount} 个可恢复引用` : "已生成，详情在诊断中查看"}`
      : null,
  ].filter((line): line is string => Boolean(line));
  return lines.length > 0 ? lines : null;
}

export function isTerminalStatus(status: string): boolean {
  return TERMINAL_STATUSES.has(status);
}

export function toggleChecked(
  setCheckedIds: Dispatch<SetStateAction<Set<string>>>,
  id: string,
) {
  setCheckedIds((current) => {
    const next = new Set(current);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    return next;
  });
}

export function applyDraftLabelsToCommitLinks(
  previews: WorkspaceResultPreview[],
  draftEdits: Record<string, WorkbenchDraftEdit>,
): WorkspaceResultPreview[] {
  return previews.map((preview) => {
    const draft = draftEdits[preview.id];
    const editedDocumentName =
      preview.kind === "document" && typeof draft?.data?.name === "string"
        ? draft.data.name.trim()
        : "";
    const editedPreview =
      typeof draft?.preview === "string" ? draft.preview.trim() : "";
    const title = editedDocumentName || editedPreview;
    if (!title) {
      return preview;
    }
    return {
      ...preview,
      title,
      roomTarget: preview.roomTarget
        ? {
            ...preview.roomTarget,
            query: title,
          }
        : preview.roomTarget,
    };
  });
}

export function generateUUID(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function statusLabel(status: string): string {
  if (status === "launching") return "启动中";
  if (status === "queued" || status === "pending") return "排队中";
  if (status === "running" || status === "cancelling") return "运行中";
  if (status === "completed") return "已完成";
  if (status === "failed_partial") return "部分完成";
  if (status === "failed") return "失败";
  if (status === "cancelled") return "已取消";
  return status || "未知";
}

export function qualityGateLabel(status: string): string {
  if (status === "pass") return "通过";
  if (status === "fail") return "失败";
  return "提醒";
}

export function qualityGateTone(status: string): CSSProperties {
  if (status === "pass") {
    return { background: "var(--wjn-evidence-soft)", color: "var(--wjn-evidence)" };
  }
  if (status === "fail") {
    return { background: "var(--wjn-error-soft)", color: "var(--wjn-error)" };
  }
  return { background: "var(--wjn-review-soft)", color: "var(--wjn-review)" };
}

export function statusTone(status: RunViewStatus | string): CSSProperties {
  if (status === "completed") {
    return { background: "var(--wjn-evidence-soft)", color: "var(--wjn-evidence)" };
  }
  if (status === "failed" || status === "failed_partial") {
    return { background: "var(--wjn-error-soft)", color: "var(--wjn-error)" };
  }
  if (status === "cancelled") {
    return { background: "rgba(15,31,53,0.06)", color: "var(--wjn-text-muted)" };
  }
  return { background: "var(--wjn-accent-soft)", color: "var(--wjn-blue)" };
}

export function kindLabel(kind: string): string {
  const meta = getWorkspaceResultKindMeta(kind);
  return meta.order === 900 ? kind : meta.label;
}

export function fieldLabel(kind: string, field: string): string {
  const labels: Record<string, string> = {
    content: "正文内容",
    name: "文件名",
    doc_kind: "文档类型",
    title: kind === "task" ? "任务标题" : "标题",
    authors: "作者",
    year: "年份",
    doi: "DOI",
    url: "URL",
    abstract: "摘要",
    category: "分类",
    confidence: "置信度",
    key: "决策键",
    value: "决策内容",
    description: "描述",
    priority: "优先级",
  };
  return labels[field] ?? field;
}

export function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function readObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function stringArrayValue(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => readString(item))
    .filter((item): item is string => Boolean(item));
}

function unknownArrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
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

export function truncate(value: string, max: number): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= max) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(0, max - 3))}...`;
}

export function formatJsonPreview(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return truncate(value, 2000);
  }
  try {
    return truncate(JSON.stringify(value, null, 2), 2400);
  } catch {
    return String(value);
  }
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export type { CommittedRoomLink };
