"use client";

/**
 * SubagentCard · Plan 2 T4
 *
 * One subagent (langgraph leaf executor) inside a phase grid.
 * Renders status pill, type label, live output preview, and tiny
 * token/duration meta. Runs on the project's "compute stage" dark
 * theme tokens (--compute-*) — distinct from the paper/ink chat theme.
 */
import type { CSSProperties } from "react";

import type { SubagentSnap } from "@/stores/workflow-store-support";

type Status =
  | "pending"
  | "running"
  | "completed"
  | "waiting"
  | "failed"
  | "cancelled"
  | "timed_out";

interface PillStyle {
  label: string;
  fg: string;
  bg: string;
  border?: string;
}

const PILL: Record<Status, PillStyle> = {
  pending: {
    label: "待启动",
    fg: "var(--compute-text-muted)",
    bg: "rgba(255, 255, 255, 0.04)",
  },
  running: {
    label: "运行中",
    fg: "var(--compute-accent-cyan)",
    bg: "var(--compute-accent-cyan-glow)",
  },
  completed: {
    label: "完成",
    fg: "var(--compute-accent-green)",
    bg: "rgba(45, 157, 120, 0.14)",
  },
  waiting: {
    label: "需要你回答",
    fg: "var(--compute-accent-gold)",
    bg: "rgba(200, 160, 80, 0.14)",
  },
  failed: {
    label: "失败 · 重试",
    fg: "var(--compute-accent-red)",
    bg: "rgba(209, 75, 75, 0.14)",
  },
  cancelled: {
    label: "已取消",
    fg: "var(--compute-text-muted)",
    bg: "rgba(255, 255, 255, 0.04)",
  },
  timed_out: {
    label: "超时",
    fg: "var(--compute-accent-red)",
    bg: "rgba(209, 75, 75, 0.14)",
  },
};

function formatTokens(n?: number): string {
  if (!n || n <= 0) return "";
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k tokens`;
  return `${n} tokens`;
}

function formatDuration(ms?: number): string {
  if (!ms || ms <= 0) return "";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return rem ? `${m}m ${rem}s` : `${m}m`;
}

const cardBaseStyle: CSSProperties = {
  background: "var(--compute-bg-elevated)",
  border: "1px solid var(--compute-border-subtle)",
  borderRadius: 8,
  color: "var(--compute-text-primary)",
};

const cardRunningStyle: CSSProperties = {
  ...cardBaseStyle,
  borderColor: "rgba(92, 151, 165, 0.35)",
  boxShadow: "0 0 0 1px rgba(92, 151, 165, 0.12) inset",
};

const cardWaitingStyle: CSSProperties = {
  ...cardBaseStyle,
  borderColor: "rgba(200, 160, 80, 0.35)",
  background:
    "linear-gradient(180deg, rgba(200, 160, 80, 0.04), rgba(17, 24, 32, 0))",
};

const cardFailedStyle: CSSProperties = {
  ...cardBaseStyle,
  borderColor: "rgba(209, 75, 75, 0.32)",
};

function styleFor(status: Status): CSSProperties {
  switch (status) {
    case "running":
      return cardRunningStyle;
    case "waiting":
      return cardWaitingStyle;
    case "failed":
    case "timed_out":
      return cardFailedStyle;
    default:
      return cardBaseStyle;
  }
}

export function SubagentCard({ subagent }: { subagent: SubagentSnap }) {
  const status = (subagent.status as Status) ?? "pending";
  const pill = PILL[status] ?? PILL.pending;
  const cardStyle = styleFor(status);

  const tokens = formatTokens(subagent.token_usage?.total);
  const duration = formatDuration(subagent.duration_ms);
  const typeLabel = subagent.subagent_type ?? "subagent";
  const idTail = subagent.task_id.slice(0, 6);

  return (
    <div
      data-testid={`subagent-card-${subagent.task_id}`}
      data-status={status}
      style={cardStyle}
      className="px-3 py-2.5 transition-colors"
    >
      {/* Header: type · id ↔ status pill */}
      <div className="flex items-center justify-between text-[11px] leading-none">
        <span
          style={{ color: "var(--compute-text-muted)" }}
          className="font-mono uppercase tracking-wider"
        >
          {typeLabel} <span className="opacity-60">· #{idTail}</span>
        </span>
        <span
          style={{ color: pill.fg, background: pill.bg }}
          className="rounded px-1.5 py-0.5 text-[10px] font-semibold leading-none"
        >
          {pill.label}
        </span>
      </div>

      {/* Live preview */}
      {subagent.output_preview && (
        <div
          style={{
            background: "rgba(0, 0, 0, 0.28)",
            color: "var(--compute-text-secondary)",
          }}
          className="mt-2 rounded px-2 py-1.5 font-mono text-[11px] leading-snug"
        >
          {subagent.output_preview}
        </div>
      )}

      {/* Waiting → chat pointer */}
      {status === "waiting" && (
        <div
          style={{
            background: "rgba(200, 160, 80, 0.06)",
            borderLeft: "2px solid rgba(200, 160, 80, 0.5)",
            color: "var(--compute-accent-gold)",
          }}
          className="mt-2 rounded-r px-2 py-1 text-[11px]"
        >
          ↩︎ 在 chat 里问了你一个问题
        </div>
      )}

      {/* Failed → error message */}
      {(status === "failed" || status === "timed_out") && subagent.error && (
        <div
          style={{ color: "var(--compute-text-secondary)" }}
          className="mt-2 text-[11px]"
        >
          {subagent.error}
        </div>
      )}

      {/* Bottom meta: tokens · duration */}
      {(tokens || duration) && (
        <div
          style={{ color: "var(--compute-text-muted)" }}
          className="mt-2 flex gap-2 text-[10px] leading-none"
        >
          {tokens && <span>{tokens}</span>}
          {duration && <span>{duration}</span>}
        </div>
      )}
    </div>
  );
}
