import type { CSSProperties } from "react";

import type { CommittedRoomLink } from "@/lib/execution-commit";
import type { RunViewStatus } from "@/lib/execution-run-view";
export {
  buildEvidenceItems,
  buildSandboxSummary,
  readReviewItems,
} from "@/lib/execution-run-view";
import { getWorkspaceResultKindMeta } from "@/lib/workspace-result-kind";

export const TERMINAL_STATUSES = new Set([
  "completed",
  "failed_partial",
  "failed",
  "cancelled",
]);

export function isTerminalStatus(status: string): boolean {
  return TERMINAL_STATUSES.has(status);
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
