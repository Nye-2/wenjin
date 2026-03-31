"use client";

import { Activity, AlertCircle, CheckCircle2, Clock3, Loader2 } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import {
  type TaskRuntimeActivityItem,
  type TaskRuntimeBlock,
  type TaskRuntimePhase,
  type TaskRuntimeState,
} from "@/lib/task-runtime";
import { cn } from "@/lib/utils";

function phaseStatusStyles(status: TaskRuntimePhase["status"]) {
  switch (status) {
    case "completed":
      return "bg-emerald-500 text-white";
    case "running":
      return "bg-[var(--accent-primary)] text-white";
    case "failed":
      return "bg-red-500 text-white";
    default:
      return "bg-[var(--bg-elevated)] text-[var(--text-muted)] border border-[var(--border-default)]";
  }
}

function activityToneStyles(tone?: TaskRuntimeActivityItem["tone"]) {
  switch (tone) {
    case "success":
      return "border-emerald-500/20 bg-emerald-500/10 text-emerald-700";
    case "warning":
      return "border-amber-500/20 bg-amber-500/10 text-amber-700";
    case "danger":
      return "border-red-500/20 bg-red-500/10 text-red-700";
    default:
      return "border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]";
  }
}

function phaseIcon(status: TaskRuntimePhase["status"]) {
  if (status === "completed") return <CheckCircle2 className="h-3.5 w-3.5" />;
  if (status === "running") return <Loader2 className="h-3.5 w-3.5 animate-spin" />;
  if (status === "failed") return <AlertCircle className="h-3.5 w-3.5" />;
  return <Clock3 className="h-3.5 w-3.5" />;
}

function BlockRenderer({ block }: { block: TaskRuntimeBlock }) {
  if (block.kind === "metrics") {
    return (
      <div className="grid grid-cols-2 gap-3">
        {block.entries.map((entry) => (
          <div
            key={entry.label}
            className="rounded-xl bg-[var(--bg-elevated)] px-3 py-3"
          >
            <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
              {entry.label}
            </p>
            <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
              {entry.value}
            </p>
          </div>
        ))}
      </div>
    );
  }

  if (block.kind === "activity") {
    return (
      <div className="space-y-3">
        {block.items.map((item, index) => (
          <div
            key={`${item.title}-${index}`}
            className={cn(
              "rounded-xl border px-3 py-3",
              activityToneStyles(item.tone)
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-medium">{item.title}</p>
                {item.description && (
                  <p className="mt-1 text-xs leading-5 opacity-90">{item.description}</p>
                )}
              </div>
              {item.timestamp && (
                <span className="shrink-0 text-[11px] opacity-70">
                  {new Date(item.timestamp).toLocaleTimeString("zh-CN", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (block.kind === "text") {
    return (
      <p className="whitespace-pre-wrap text-sm leading-6 text-[var(--text-secondary)]">
        {block.content}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {block.items.map((item, index) => (
        <div
          key={`${item.title}-${index}`}
          className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-[var(--text-primary)]">
                {item.title}
              </p>
              {item.description && (
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  {item.description}
                </p>
              )}
              {item.meta && (
                <p className="mt-2 text-[11px] text-[var(--text-muted)]">
                  {item.meta}
                </p>
              )}
            </div>
            {item.badge && (
              <span className="rounded-full bg-[var(--accent-primary)]/10 px-2 py-0.5 text-[11px] font-medium text-[var(--accent-primary)]">
                {item.badge}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

interface TaskRuntimePanelProps {
  runtime: TaskRuntimeState | null;
  isRunning: boolean;
  status?: string | null;
  error?: string | null;
  title?: string;
  emptyTitle?: string;
  emptyDescription?: string;
  className?: string;
}

export function TaskRuntimePanel({
  runtime,
  isRunning,
  status,
  error,
  title,
  emptyTitle = "运行时面板",
  emptyDescription = "长任务执行时，这里会显示阶段进度和中间结果。",
  className,
}: TaskRuntimePanelProps) {
  const phases = runtime?.phases || [];
  const blocks = runtime?.blocks || [];
  const currentPhase =
    runtime?.current_phase && phases.length > 0
      ? phases.find((phase) => phase.id === runtime.current_phase)
      : null;
  const overallProgress =
    phases.length > 0
      ? Math.round(
          phases.reduce((sum, phase) => sum + (phase.progress || 0), 0) / phases.length
        )
      : isRunning
        ? 15
        : 0;

  return (
    <section
      className={cn(
        "route-card rounded-[1.75rem] p-5",
        className
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-[var(--accent-primary)]" />
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">
              {title || runtime?.title || emptyTitle}
            </h3>
          </div>
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            {error || status || currentPhase?.description || emptyDescription}
          </p>
        </div>
        {(isRunning || runtime) && (
          <span className="shrink-0 rounded-full border border-[var(--border-default)] bg-white/80 px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)]">
            {overallProgress}%
          </span>
        )}
      </div>

      {(isRunning || runtime) && (
        <div className="mt-4">
          <Progress value={overallProgress} className="h-2 bg-[var(--bg-elevated)]" />
        </div>
      )}

      {phases.length > 0 && (
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {phases.map((phase) => (
            <div
              key={phase.id}
            className="rounded-2xl border border-[var(--border-default)] bg-white/78 px-3 py-3"
          >
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "inline-flex h-7 w-7 items-center justify-center rounded-full text-xs",
                    phaseStatusStyles(phase.status)
                  )}
                >
                  {phaseIcon(phase.status)}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-[var(--text-primary)]">
                    {phase.label}
                  </p>
                  {phase.description && (
                    <p className="text-[11px] text-[var(--text-muted)]">
                      {phase.description}
                    </p>
                  )}
                </div>
              </div>
              {typeof phase.progress === "number" && (
                <div className="mt-3">
                  <Progress
                    value={phase.progress}
                    className="h-1.5 bg-[var(--bg-surface)]"
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {blocks.length > 0 ? (
        <div className="mt-5 space-y-4">
          {blocks.map((block) => (
            <div
              key={block.id}
              className="rounded-2xl border border-[var(--border-default)] bg-white/76 p-4"
            >
              <div className="mb-3">
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  {block.title}
                </p>
                {block.description && (
                  <p className="mt-1 text-xs text-[var(--text-muted)]">
                    {block.description}
                  </p>
                )}
              </div>
              <BlockRenderer block={block} />
            </div>
          ))}
        </div>
      ) : (
        !isRunning &&
        !error && (
          <div className="mt-4 rounded-2xl border border-dashed border-[var(--border-default)] px-4 py-6 text-center">
            <p className="text-sm text-[var(--text-secondary)]">{emptyDescription}</p>
          </div>
        )
      )}
    </section>
  );
}
