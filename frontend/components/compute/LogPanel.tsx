"use client";

import { Terminal } from "lucide-react";
import { cn } from "@/lib/utils";
import { readString, logToneClass } from "./utils";
import type { ComputeLogProjection } from "@/lib/api";

interface LogPanelProps {
  logs: ComputeLogProjection[];
}

export function LogPanel({ logs }: LogPanelProps) {
  return (
    <section className="rounded-2xl border border-[var(--border-default)] bg-white/78 p-4">
      <div className="flex items-center gap-2">
        <Terminal className="h-4 w-4 text-[var(--accent-primary)]" />
        <h4 className="text-sm font-semibold text-[var(--text-primary)]">
          执行日志
        </h4>
      </div>
      <div className="mt-3 space-y-2">
        {logs.length > 0 ? (
          logs.slice(0, 8).map((log) => (
            <div
              key={log.id}
              className={cn(
                "rounded-xl border px-3 py-2",
                logToneClass(log.level)
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                  {log.title}
                </p>
                <span className="shrink-0 text-[11px]">{log.level}</span>
              </div>
              <p className="mt-1 line-clamp-4 whitespace-pre-wrap text-xs leading-5">
                {log.message}
              </p>
              {readString(log.timestamp) ? (
                <p className="mt-1 truncate text-[11px] text-[var(--text-muted)]">
                  {readString(log.timestamp)}
                </p>
              ) : null}
            </div>
          ))
        ) : (
          <p className="rounded-xl border border-dashed border-[var(--border-default)] px-3 py-4 text-center text-xs text-[var(--text-muted)]">
            当前执行还没有结构化日志。
          </p>
        )}
      </div>
    </section>
  );
}
