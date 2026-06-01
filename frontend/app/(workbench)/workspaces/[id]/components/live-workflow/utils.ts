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
    .filter(([, state]) => Boolean(state.output || state.output_preview || state.tool_calls?.length))
    .map(([nodeId, state]) => {
      const node = nodeById.get(nodeId);
      const output = state.output ?? {};
      const title = node?.label ?? node?.task ?? nodeId;
      const sandbox = buildSandboxSummary(state);
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
  return [...outputItems, ...nodeItems];
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
  const lines = [
    `操作：${readString(output?.operation) ?? readString(tool?.name) ?? "sandbox"}`,
    `状态：${readString(output?.status) ?? readString(tool?.status) ?? state.status ?? "unknown"}`,
    output?.exit_code !== undefined || tool?.exit_code !== undefined
      ? `Exit code：${String(output?.exit_code ?? tool?.exit_code)}`
      : null,
    readString(output?.docker_image) || readString(tool?.docker_image)
      ? `镜像：${readString(output?.docker_image) ?? readString(tool?.docker_image)}`
      : null,
    readString(output?.stdout) ? `Stdout：${truncate(readString(output?.stdout)!, 120)}` : null,
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
    return { background: "rgba(34, 197, 94, 0.12)", color: "var(--v2-status-success-deep)" };
  }
  if (status === "fail") {
    return { background: "rgba(220, 38, 38, 0.1)", color: "var(--v2-status-error)" };
  }
  return { background: "rgba(245, 158, 11, 0.13)", color: "#92400E" };
}

export function statusTone(status: RunViewStatus | string): CSSProperties {
  if (status === "completed") {
    return { background: "rgba(34, 197, 94, 0.12)", color: "var(--v2-status-success-deep)" };
  }
  if (status === "failed" || status === "failed_partial") {
    return { background: "rgba(220, 38, 38, 0.1)", color: "var(--v2-status-error)" };
  }
  if (status === "cancelled") {
    return { background: "rgba(20, 20, 30, 0.06)", color: "var(--v2-text-tertiary)" };
  }
  return { background: "var(--v2-accent-purple-100)", color: "var(--v2-accent-purple-700)" };
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
