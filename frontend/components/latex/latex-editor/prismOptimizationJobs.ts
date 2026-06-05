import type { ExecutionRecord } from "@/lib/api";

export type PrismOptimizationJobStatus =
  | "launching"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "advisory";

export interface PrismOptimizationJob {
  id: string;
  feedbackId: string;
  executionId?: string | null;
  status: PrismOptimizationJobStatus;
  filePath: string;
  scope: "selection" | "section" | "document";
  instruction: string;
  selectedText: string;
  createdAt: string;
  error?: string | null;
}

export const TERMINAL_PRISM_EXECUTION_STATUSES = new Set([
  "completed",
  "failed_partial",
  "failed",
  "cancelled",
]);

export function createPrismOptimizationJobId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `prism-job-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function trimSnippet(value: string, limit = 120): string {
  const compact = value.replace(/\s+/g, " ").trim();
  if (compact.length <= limit) {
    return compact;
  }
  return `${compact.slice(0, limit - 1).trim()}…`;
}

export function jobStatusFromExecution(record: ExecutionRecord | null | undefined): PrismOptimizationJobStatus | null {
  if (!record) {
    return null;
  }
  if (record.status === "completed") {
    return "completed";
  }
  if (record.status === "failed_partial") {
    return record.review_items?.length ? "completed" : "failed";
  }
  if (record.status === "cancelled") {
    return "cancelled";
  }
  if (record.status === "failed") {
    return "failed";
  }
  return "running";
}

export function prismJobStatusLabel(status: PrismOptimizationJobStatus): string {
  if (status === "completed") return "已生成待审修改";
  if (status === "failed") return "优化失败";
  if (status === "cancelled") return "已取消";
  if (status === "advisory") return "需要稍后重试";
  if (status === "running") return "Agent 正在优化";
  return "正在启动 Agent";
}

export function prismExecutionNodeLabel(status?: string): string {
  if (status === "completed") return "完成";
  if (status === "failed") return "失败";
  if (status === "running") return "运行中";
  return "等待";
}
