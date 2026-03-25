"use client";

import { AlertTriangle, ArrowRight, Clock3, History, KanbanSquare } from "lucide-react";
import type { WorkspaceSummaryData } from "@/lib/api";
import { cn } from "@/lib/utils";

interface TaskSummaryStripProps {
  summary: WorkspaceSummaryData | null;
}

function phaseTone(status: string) {
  switch (status) {
    case "failed":
      return "bg-red-500/10 text-red-600";
    case "in_progress":
      return "bg-amber-500/10 text-amber-600";
    case "completed":
      return "bg-emerald-500/10 text-emerald-600";
    default:
      return "bg-slate-500/10 text-slate-600";
  }
}

function activityTimeLabel(value?: string | null) {
  if (!value) {
    return "暂无活动";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "最近更新";
  }

  return date.toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function TaskSummaryStrip({ summary }: TaskSummaryStripProps) {
  if (!summary) {
    return (
      <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)] px-5 py-4">
        <p className="text-sm text-[var(--text-muted)]">正在汇总当前任务状态...</p>
      </section>
    );
  }

  const primaryRisk = summary.risk_items[0] ?? null;

  return (
    <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)] px-5 py-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)]">
              <KanbanSquare className="h-3.5 w-3.5" />
              任务驾驶舱
            </span>
            <span
              className={cn(
                "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium",
                phaseTone(summary.current_phase.status)
              )}
            >
              当前阶段: {summary.current_phase.title}
            </span>
          </div>
          <p className="mt-3 text-base font-medium text-[var(--text-primary)]">
            {summary.headline}
          </p>
        </div>
        <div className="shrink-0 rounded-xl bg-[var(--bg-elevated)] px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
            总体进度
          </p>
          <p className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">
            {summary.progress.percent}%
          </p>
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            已完成 {summary.progress.completed}/{summary.progress.total} 个模块
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl bg-[var(--bg-elevated)] px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
            当前阶段
          </p>
          <p className="mt-2 text-sm font-medium text-[var(--text-primary)]">
            {summary.current_phase.title}
          </p>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            {summary.current_phase.description || "当前阶段信息已就绪。"}
          </p>
        </div>

        <div className="rounded-xl bg-[var(--bg-elevated)] px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
            下一步建议
          </p>
          <p className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-[var(--text-primary)]">
            {summary.next_step?.title || "当前暂无待处理步骤"}
            {summary.next_step && <ArrowRight className="h-3.5 w-3.5 text-[var(--accent-primary)]" />}
          </p>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            {summary.next_step?.reason || "当前没有阻塞项，可以继续在 chat 中自由推进。"}
          </p>
        </div>

        <div className="rounded-xl bg-[var(--bg-elevated)] px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
            最近活动
          </p>
          <p className="mt-2 text-sm font-medium text-[var(--text-primary)]">
            {summary.recent_activity?.title || "暂无近期活动"}
          </p>
          <p className="mt-1 flex items-center gap-1 text-xs leading-5 text-[var(--text-secondary)]">
            <History className="h-3.5 w-3.5 text-[var(--text-muted)]" />
            {summary.recent_activity?.summary || activityTimeLabel(summary.recent_activity?.occurred_at)}
          </p>
        </div>

        <div className="rounded-xl bg-[var(--bg-elevated)] px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
            风险提醒
          </p>
          <p className="mt-2 text-sm font-medium text-[var(--text-primary)]">
            {primaryRisk ? primaryRisk.title : "当前无明显风险"}
          </p>
          <p className="mt-1 flex items-center gap-1 text-xs leading-5 text-[var(--text-secondary)]">
            {primaryRisk ? (
              <>
                <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                共 {summary.risk_items.length} 条提醒
              </>
            ) : (
              <>
                <Clock3 className="h-3.5 w-3.5 text-[var(--text-muted)]" />
                可以继续推进主线任务
              </>
            )}
          </p>
        </div>
      </div>
    </section>
  );
}
