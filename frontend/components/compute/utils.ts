"use client";

import type {
  ComputeFileProjection,
  ComputePrismProjection,
  ComputeReviewGateProjection,
} from "@/lib/api";
import type {
  TaskRuntimeBlock,
  TaskRuntimePhase,
  TaskRuntimePhaseStatus,
  TaskRuntimeState,
} from "@/lib/task-runtime";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function readNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function readFileChangeKey(value: Record<string, unknown>): string | null {
  return readString(value.logical_key);
}

export function isRunningStatus(status?: string | null): boolean {
  return ["launching", "pending", "running", "awaiting_user_input"].includes(
    String(status || "")
  );
}

export function statusLabel(status?: string | null): string {
  switch (status) {
    case "launching":
      return "启动中";
    case "pending":
      return "排队中";
    case "running":
      return "运行中";
    case "awaiting_user_input":
      return "等待补充";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    case "advisory":
      return "需处理";
    default:
      return status || "未知";
  }
}

export function sandboxStatusLabel(status?: string | null): string {
  switch (status) {
    case "bound":
      return "已绑定";
    case "derived":
      return "已产出";
    case "required":
      return "必需";
    case "unbound":
      return "未绑定";
    default:
      return status || "未知";
  }
}

export function reviewStatusLabel(status?: string | null): string {
  switch (status) {
    case "clear":
      return "已通过";
    case "awaiting_user":
      return "等待用户";
    case "failed":
      return "未通过";
    default:
      return status || "无";
  }
}

export function prismStatusLabel(status?: string | null): string {
  switch (status) {
    case "ready":
      return "就绪";
    case "compile_failed":
      return "编译失败";
    case "pending_changes":
      return "待确认";
    case "blocked_by_review":
      return "被审核阻塞";
    default:
      return status || "未关联";
  }
}

export function fileLabel(file: ComputeFileProjection): string {
  return file.label || readString(file.path) || "未命名文件";
}

export function fileMeta(file: ComputeFileProjection): string {
  const parts: string[] = [];
  if (readString(file.kind)) parts.push(file.kind);
  if (readString(file.source)) parts.push(file.source);
  return parts.join(" · ") || "沙箱文件";
}

export function logToneClass(level?: string | null): string {
  switch (level) {
    case "error":
      return "border-compute-red/20 bg-compute-red/5";
    case "warn":
    case "warning":
      return "border-compute-gold/20 bg-compute-gold/5";
    case "info":
    case "success":
      return "border-compute-border bg-compute-elevated";
    case "debug":
      return "border-compute-border/50 bg-compute-surface";
    default:
      return "border-compute-border bg-compute-elevated";
  }
}

export function reviewTone(
  gate: ComputeReviewGateProjection | null
): "default" | "success" | "warning" | "danger" {
  if (!gate) return "default";
  if (gate.status === "clear") return "success";
  if (gate.status === "failed") return "danger";
  if (gate.required) return "warning";
  return "default";
}

export function prismTone(
  prism: ComputePrismProjection | null
): "default" | "success" | "warning" | "danger" {
  if (!prism) return "default";
  if (prism.status === "ready") return "success";
  if (prism.status === "compile_failed") return "danger";
  if (prism.status === "pending_changes" || prism.status === "blocked_by_review")
    return "warning";
  return "default";
}

function normalizePhaseStatus(value: unknown): TaskRuntimePhaseStatus {
  const s = readString(value);
  if (s === "pending" || s === "running" || s === "completed" || s === "failed") {
    return s;
  }
  return "pending";
}

export function normalizePhase(value: unknown): TaskRuntimePhase | null {
  if (!isRecord(value)) return null;
  const phaseId = readString(value.id) ?? readString(value.phase_id);
  if (!phaseId) return null;
  return {
    id: phaseId,
    label: readString(value.label) ?? readString(value.name) ?? phaseId,
    status: normalizePhaseStatus(value.status),
    description: readString(value.description) ?? undefined,
    progress: readNumber(value.progress) ?? undefined,
  };
}

function normalizeBlockKind(value: unknown): TaskRuntimeBlock["kind"] | null {
  const k = readString(value);
  if (k === "metrics" || k === "list" || k === "activity" || k === "text") {
    return k;
  }
  return null;
}

export function normalizeBlock(value: unknown): TaskRuntimeBlock | null {
  if (!isRecord(value)) return null;
  const blockId = readString(value.id) ?? readString(value.block_id);
  const kind = normalizeBlockKind(value.kind);
  if (!blockId || !kind) return null;

  const base = {
    id: blockId,
    phase_id: readString(value.phase_id) ?? undefined,
    kind,
    title: readString(value.title) ?? "",
    description: readString(value.description) ?? undefined,
  };

  switch (kind) {
    case "metrics":
      return {
        ...base,
        kind: "metrics",
        entries: Array.isArray(value.entries)
          ? value.entries
              .filter(isRecord)
              .map((e) => ({
                label: readString(e.label) ?? "",
                value: readString(e.value) ?? "",
              }))
          : [],
      };
    case "list":
      return {
        ...base,
        kind: "list",
        items: Array.isArray(value.items)
          ? value.items
              .filter(isRecord)
              .map((item) => ({
                title: readString(item.title) ?? "",
                description: readString(item.description) ?? undefined,
                meta: readString(item.meta) ?? undefined,
                badge: readString(item.badge) ?? null,
              }))
          : [],
      };
    case "activity":
      return {
        ...base,
        kind: "activity",
        items: Array.isArray(value.items)
          ? value.items
              .filter(isRecord)
              .map((item) => {
                const toneStr = readString(item.tone);
                const tone:
                  | "info"
                  | "success"
                  | "warning"
                  | "danger"
                  | undefined =
                  toneStr === "info" ||
                  toneStr === "success" ||
                  toneStr === "warning" ||
                  toneStr === "danger"
                    ? toneStr
                    : undefined;
                return {
                  title: readString(item.title) ?? "",
                  description: readString(item.description) ?? undefined,
                  tone,
                  timestamp: readString(item.timestamp) ?? undefined,
                };
              })
          : [],
      };
    case "text":
      return {
        ...base,
        kind: "text",
        content: readString(value.content) ?? "",
      };
    default:
      return null;
  }
}

export function buildRuntimeState(
  projection: { runtime_blocks?: unknown[]; phases?: unknown[] } | null,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _activeExecution: { status?: string | null } | null
): TaskRuntimeState {
  const blocks: TaskRuntimeBlock[] = [];
  if (Array.isArray(projection?.runtime_blocks)) {
    for (const item of projection.runtime_blocks) {
      const block = normalizeBlock(item);
      if (block) blocks.push(block);
    }
  }
  const phases: TaskRuntimePhase[] = [];
  if (Array.isArray(projection?.phases)) {
    for (const item of projection.phases) {
      const phase = normalizePhase(item);
      if (phase) phases.push(phase);
    }
  }
  return {
    phases,
    blocks,
    current_phase:
      phases.find((p) => p.status === "running")?.id ??
      phases.find((p) => p.status === "pending")?.id ??
      phases[phases.length - 1]?.id,
    updated_at: undefined,
  };
}

export function formatShortId(value?: string | null): string {
  if (!value) return "—";
  if (value.length <= 12) return value;
  return `${value.slice(0, 6)}…${value.slice(-4)}`;
}
