"use client";

import { FileText } from "lucide-react";
import { readString, formatShortId } from "./utils";

interface TaskArtifactPanelProps {
  tasks: Array<{
    task_id?: string | null;
    status?: string | null;
    message?: string | null;
  }>;
  artifactIds: string[];
}

export function TaskArtifactPanel({ tasks, artifactIds }: TaskArtifactPanelProps) {
  return (
    <section className="rounded-2xl border border-[var(--border-default)] bg-white/78 p-4">
      <div className="flex items-center gap-2">
        <FileText className="h-4 w-4 text-[var(--accent-primary)]" />
        <h4 className="text-sm font-semibold text-[var(--text-primary)]">
          任务与产物
        </h4>
      </div>
      <div className="mt-3 space-y-2">
        {tasks.slice(0, 5).map((task) => (
          <div
            key={String(task.task_id)}
            className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2"
          >
            <div className="flex items-center justify-between gap-3">
              <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                {formatShortId(readString(task.task_id))}
              </p>
              <span className="shrink-0 text-[11px] text-[var(--text-muted)]">
                {String(task.status || "unknown")}
              </span>
            </div>
            {readString(task.message) ? (
              <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">
                {readString(task.message)}
              </p>
            ) : null}
          </div>
        ))}
        {tasks.length === 0 ? (
          <p className="rounded-xl border border-dashed border-[var(--border-default)] px-3 py-4 text-center text-xs text-[var(--text-muted)]">
            当前 Compute projection 暂无任务记录。
          </p>
        ) : null}
        {artifactIds.length > 0 ? (
          <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2">
            <p className="text-xs font-medium text-[var(--text-primary)]">
              Artifact IDs
            </p>
            <p className="mt-1 line-clamp-3 text-[11px] leading-5 text-[var(--text-muted)]">
              {artifactIds.join(", ")}
            </p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
