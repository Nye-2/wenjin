"use client";

import { Loader2 } from "lucide-react";
import type { ThreadMessageBlock } from "@/lib/api";

export function TaskProgressBlock({
  block,
  isStreaming,
}: {
  block: ThreadMessageBlock;
  isStreaming?: boolean;
}) {
  const data = block.data ?? {};
  const status =
    typeof data.status === "string" ? data.status : "running";
  const phase =
    typeof data.phase === "string" ? data.phase : null;
  const progress =
    typeof data.progress === "number" && Number.isFinite(data.progress)
      ? Math.max(0, Math.min(100, data.progress))
      : null;
  const message =
    typeof data.message === "string" ? data.message : null;

  return (
    <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)]/70 px-3 py-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-[var(--text-primary)]">
            {block.title || "Agent 正在处理"}
          </p>
          {message ? (
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              {message}
            </p>
          ) : null}
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-600">
          {isStreaming || status === "running" ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : null}
          {phase || (status === "running" ? "运行中" : status)}
        </span>
      </div>

      {progress !== null ? (
        <div className="mt-3">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]">
            <div
              className="h-full rounded-full bg-amber-500 transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="mt-1 text-[11px] text-[var(--text-muted)]">
            进度 {progress}%
          </p>
        </div>
      ) : null}

      <div className="mt-2 flex flex-wrap gap-2">
        <span className="rounded-full bg-[var(--accent-primary)]/10 px-2 py-1 text-[11px] font-medium text-[var(--accent-primary)]">
          右侧工作面板会持续更新执行过程
        </span>
      </div>
    </div>
  );
}
