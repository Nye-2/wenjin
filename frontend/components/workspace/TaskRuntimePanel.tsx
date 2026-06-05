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
      return "bg-[var(--wjn-navy)] text-white";
    case "failed":
      return "bg-red-500 text-white";
    default:
      return "bg-[var(--wjn-surface)] text-[var(--wjn-text-muted)] border border-[var(--wjn-line)]";
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
      return "border-[var(--wjn-line)] bg-[var(--wjn-surface)] text-[var(--wjn-text-secondary)]";
  }
}

function phaseIcon(status: TaskRuntimePhase["status"]) {
  if (status === "completed") return <CheckCircle2 className="h-3.5 w-3.5" />;
  if (status === "running") return <Loader2 className="h-3.5 w-3.5 animate-spin" />;
  if (status === "failed") return <AlertCircle className="h-3.5 w-3.5" />;
  return <Clock3 className="h-3.5 w-3.5" />;
}

function normalizePhaseToken(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  return value.toLowerCase().replace(/[_\s-]+/g, "");
}

function blockMatchesPhase(
  block: TaskRuntimeBlock,
  phase: TaskRuntimePhase
): boolean {
  const phaseIdToken = normalizePhaseToken(phase.id);
  const phaseLabelToken = normalizePhaseToken(phase.label);
  const phaseTokenSet = new Set([phaseIdToken, phaseLabelToken].filter(Boolean));

  const phaseIdValue =
    typeof block.phase_id === "string" ? block.phase_id.trim() : "";
  if (phaseIdValue) {
    const blockPhaseToken = normalizePhaseToken(phaseIdValue);
    if (phaseTokenSet.has(blockPhaseToken)) {
      return true;
    }
    return Array.from(phaseTokenSet).some(
      (token) =>
        token.includes(blockPhaseToken) || blockPhaseToken.includes(token)
    );
  }

  const sourceTokens = [
    normalizePhaseToken(block.id),
    normalizePhaseToken(block.title),
    normalizePhaseToken(block.description),
  ].filter(Boolean);

  if (sourceTokens.length === 0) {
    return false;
  }

  return sourceTokens.some((sourceToken) =>
    Array.from(phaseTokenSet).some(
      (phaseToken) =>
        sourceToken.includes(phaseToken) || phaseToken.includes(sourceToken)
    )
  );
}

function BlockRenderer({ block }: { block: TaskRuntimeBlock }) {
  if (block.kind === "metrics") {
    return (
      <div className="grid grid-cols-2 gap-3">
        {block.entries.map((entry) => (
          <div
            key={entry.label}
            className="rounded-xl bg-[var(--wjn-surface)] px-3 py-3"
          >
            <p className="text-[11px] uppercase tracking-wide text-[var(--wjn-text-muted)]">
              {entry.label}
            </p>
            <p className="mt-1 text-sm font-medium text-[var(--wjn-text)]">
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
      <p className="whitespace-pre-wrap text-sm leading-6 text-[var(--wjn-text-secondary)]">
        {block.content}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {block.items.map((item, index) => (
        <div
          key={`${item.title}-${index}`}
          className="rounded-xl border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-3 py-3"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-[var(--wjn-text)]">
                {item.title}
              </p>
              {item.description && (
                <p className="mt-1 text-xs leading-5 text-[var(--wjn-text-secondary)]">
                  {item.description}
                </p>
              )}
              {item.meta && (
                <p className="mt-2 text-[11px] text-[var(--wjn-text-muted)]">
                  {item.meta}
                </p>
              )}
            </div>
            {item.badge && (
              <span className="rounded-full bg-[var(--wjn-navy)]/10 px-2 py-0.5 text-[11px] font-medium text-[var(--wjn-navy)]">
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
  selectedPhaseId?: string | null;
  onSelectPhase?: (phaseId: string | null) => void;
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
  selectedPhaseId = null,
  onSelectPhase,
  title,
  emptyTitle = "运行时面板",
  emptyDescription = "长任务执行时，这里会显示阶段进度和中间结果。",
  className,
}: TaskRuntimePanelProps) {
  const phases = runtime?.phases || [];
  const blocks = runtime?.blocks || [];
  const effectiveSelectedPhaseId =
    selectedPhaseId && phases.some((phase) => phase.id === selectedPhaseId)
      ? selectedPhaseId
      : null;
  const currentPhase =
    runtime?.current_phase && phases.length > 0
      ? phases.find((phase) => phase.id === runtime.current_phase)
      : null;
  const focusPhase =
    effectiveSelectedPhaseId && phases.length > 0
      ? phases.find((phase) => phase.id === effectiveSelectedPhaseId) ?? currentPhase
      : currentPhase;
  const matchedBlocks =
    focusPhase && blocks.length > 0
      ? blocks.filter((block) => blockMatchesPhase(block, focusPhase))
      : blocks;
  const hasPhaseFilteredBlocks =
    Boolean(focusPhase) && matchedBlocks.length > 0;
  const visibleBlocks = hasPhaseFilteredBlocks ? matchedBlocks : blocks;
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
            <Activity className="h-4 w-4 text-[var(--wjn-navy)]" />
            <h3 className="text-sm font-semibold text-[var(--wjn-text)]">
              {title || runtime?.title || emptyTitle}
            </h3>
          </div>
          <p className="mt-1 text-xs text-[var(--wjn-text-muted)]">
            {error || status || focusPhase?.description || emptyDescription}
          </p>
        </div>
        {(isRunning || runtime) && (
          <span className="shrink-0 rounded-full border border-[var(--wjn-line)] bg-white/80 px-2.5 py-1 text-xs font-medium text-[var(--wjn-navy)]">
            {overallProgress}%
          </span>
        )}
      </div>

      {(isRunning || runtime) && (
        <div className="mt-4">
          <Progress value={overallProgress} className="h-2 bg-[var(--wjn-surface)]" />
        </div>
      )}

      {phases.length > 0 && (
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {phases.map((phase) => {
            const isSelected = effectiveSelectedPhaseId === phase.id;
            const body = (
              <>
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
                    <p className="text-sm font-medium text-[var(--wjn-text)]">
                      {phase.label}
                    </p>
                    {phase.description && (
                      <p className="text-[11px] text-[var(--wjn-text-muted)]">
                        {phase.description}
                      </p>
                    )}
                  </div>
                </div>
                {typeof phase.progress === "number" && (
                  <div className="mt-3">
                    <Progress
                      value={phase.progress}
                      className="h-1.5 bg-[var(--wjn-surface-subtle)]"
                    />
                  </div>
                )}
              </>
            );

            const containerClass = cn(
              "rounded-2xl border bg-white/78 px-3 py-3",
              isSelected
                ? "border-[var(--wjn-navy)]/40 ring-1 ring-[var(--wjn-navy)]/20"
                : "border-[var(--wjn-line)]",
              onSelectPhase
                ? "cursor-pointer text-left transition-colors hover:border-[var(--wjn-navy)]/25"
                : ""
            );

            if (!onSelectPhase) {
              return (
                <div key={phase.id} className={containerClass}>
                  {body}
                </div>
              );
            }

            return (
              <button
                key={phase.id}
                type="button"
                onClick={() => onSelectPhase(isSelected ? null : phase.id)}
                className={containerClass}
              >
                {body}
              </button>
            );
          })}
        </div>
      )}

      {focusPhase && onSelectPhase ? (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-[var(--wjn-navy)]/25 bg-[var(--wjn-navy)]/10 px-2.5 py-1 text-[10px] text-[var(--wjn-navy)]">
            阶段聚焦: {focusPhase.label}
          </span>
          <span className="rounded-full border border-[var(--wjn-line)] bg-white/80 px-2.5 py-1 text-[10px] text-[var(--wjn-text-muted)]">
            {hasPhaseFilteredBlocks
              ? `匹配 ${matchedBlocks.length}/${blocks.length} 个运行块`
              : "未找到阶段专属运行块，已显示全部"}
          </span>
          <button
            type="button"
            onClick={() => onSelectPhase(null)}
            className="rounded-full border border-[var(--wjn-line)] bg-white/80 px-2.5 py-1 text-[10px] text-[var(--wjn-text-secondary)] transition-colors hover:bg-[var(--wjn-surface-subtle)]"
          >
            清除聚焦
          </button>
        </div>
      ) : null}

      {visibleBlocks.length > 0 ? (
        <div className="mt-5 space-y-4">
          {visibleBlocks.map((block) => (
            <div
              key={block.id}
              className={cn(
                "rounded-2xl border bg-white/76 p-4",
                hasPhaseFilteredBlocks && focusPhase && blockMatchesPhase(block, focusPhase)
                  ? "border-[var(--wjn-navy)]/30 ring-1 ring-[var(--wjn-navy)]/12"
                  : "border-[var(--wjn-line)]"
              )}
            >
              <div className="mb-3">
                <p className="text-sm font-medium text-[var(--wjn-text)]">
                  {block.title}
                </p>
                {block.description && (
                  <p className="mt-1 text-xs text-[var(--wjn-text-muted)]">
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
          <div className="mt-4 rounded-2xl border border-dashed border-[var(--wjn-line)] px-4 py-6 text-center">
            <p className="text-sm text-[var(--wjn-text-secondary)]">{emptyDescription}</p>
          </div>
        )
      )}
    </section>
  );
}
