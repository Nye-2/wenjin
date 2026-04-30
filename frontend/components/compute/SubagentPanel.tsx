"use client";

import { Layers3 } from "lucide-react";
import { readString } from "./utils";

interface SubagentPanelProps {
  subagents: Array<{
    task_id?: string | null;
    subagent_type?: string | null;
    status?: string | null;
    output_preview?: string | null;
  }>;
}

export function SubagentPanel({ subagents }: SubagentPanelProps) {
  return (
    <section className="compute-card p-4">
      <div className="flex items-center gap-2">
        <Layers3 className="h-4 w-4 text-compute-cyan" />
        <h4 className="text-sm font-semibold text-compute-text-primary">
          子代理
        </h4>
      </div>
      <div className="mt-3 space-y-2">
        {subagents.length > 0 ? (
          subagents.slice(0, 8).map((subagent) => (
            <div
              key={String(subagent.task_id)}
              className="rounded-xl border border-compute-border bg-compute-surface px-3 py-2"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="truncate text-sm font-medium text-compute-text-primary">
                  {String(subagent.subagent_type || "子代理")}
                </p>
                <span className="shrink-0 text-[11px] text-compute-text-muted">
                  {String(subagent.status || "未知")}
                </span>
              </div>
              {readString(subagent.output_preview) ? (
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-compute-text-secondary">
                  {readString(subagent.output_preview)}
                </p>
              ) : null}
            </div>
          ))
        ) : (
          <p className="rounded-xl border border-dashed border-compute-border px-3 py-4 text-center text-xs text-compute-text-muted">
            当前执行未启动子代理。
          </p>
        )}
      </div>
    </section>
  );
}
