"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { type ExecutionSession } from "@/lib/api";
import { cn } from "@/lib/utils";

interface NextStepAction {
  title: string;
  description?: string | null;
  reason?: string | null;
}

interface WorkspaceProjectStatusStripProps {
  currentPhaseTitle: string;
  currentPhaseDescription?: string | null;
  headline?: string | null;
  activeSkillLabel?: string | null;
  artifactsCount: number;
  activeExecution: ExecutionSession | null;
  nextStepAction: NextStepAction | null;
  prismPendingChanges?: number;
  prismAppliedChanges?: number;
}

function getExecutionStatusLabel(
  status: string | null | undefined
): string {
  switch (status) {
    case "running":
    case "pending":
    case "launching":
      return "Agent 正在工作";
    case "awaiting_user_input":
      return "等待你补充";
    case "failed":
      return "任务失败";
    case "completed":
      return "已完成";
    default:
      return "无任务";
  }
}

function getExecutionStatusTone(
  status: string | null | undefined
): string {
  switch (status) {
    case "running":
    case "pending":
    case "launching":
      return "text-amber-700 bg-amber-500/10 border-amber-500/20";
    case "awaiting_user_input":
      return "text-sky-700 bg-sky-500/10 border-sky-500/20";
    case "failed":
      return "text-red-700 bg-red-500/10 border-red-500/20";
    case "completed":
      return "text-emerald-700 bg-emerald-500/10 border-emerald-500/20";
    default:
      return "text-[var(--text-muted)] bg-[var(--bg-muted)] border-[var(--border-default)]";
  }
}

function getPrismStatusLabel(
  pending: number | undefined,
  applied: number | undefined
): string | null {
  if (pending && pending > 0) {
    return `主稿有待确认修改 ${pending}`;
  }
  if (applied && applied > 0) {
    return `主稿已写入 ${applied}`;
  }
  return null;
}

function getPrismStatusTone(): string {
  return "text-compute-gold bg-compute-gold/10 border-compute-gold/20";
}

export function WorkspaceProjectStatusStrip({
  currentPhaseTitle,
  currentPhaseDescription,
  headline,
  activeSkillLabel,
  artifactsCount,
  activeExecution,
  nextStepAction,
  prismPendingChanges,
  prismAppliedChanges,
}: WorkspaceProjectStatusStripProps) {
  const [expanded, setExpanded] = useState(false);

  const executionStatus = getExecutionStatusLabel(activeExecution?.status);
  const executionTone = getExecutionStatusTone(activeExecution?.status);
  const prismLabel = getPrismStatusLabel(prismPendingChanges, prismAppliedChanges);
  const prismTone = getPrismStatusTone();

  return (
    <div className="border-b border-[var(--border-default)] bg-[rgba(251,248,242,0.94)] px-4 py-2">
      <div className="flex items-center gap-3">
        {/* Stage indicator */}
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-[var(--brand-brass)]" />
          <span className="text-sm font-medium text-[var(--text-primary)]">
            {currentPhaseTitle}
          </span>
        </div>

        {activeSkillLabel ? (
          <span className="rounded-full border border-[var(--accent-primary)]/18 bg-[var(--accent-primary)]/8 px-2 py-0.5 text-[10px] font-medium text-[var(--accent-primary)]">
            {activeSkillLabel}
          </span>
        ) : null}

        {/* Execution status badge */}
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-[10px] font-medium",
            executionTone
          )}
        >
          {executionStatus}
        </span>

        {/* Stats */}
        <span className="text-xs text-[var(--text-muted)]">
          产物 {artifactsCount}
        </span>

        {/* Prism status badge */}
        {prismLabel ? (
          <span
            className={cn(
              "rounded-full border px-2 py-0.5 text-[10px] font-medium",
              prismTone
            )}
          >
            {prismLabel}
          </span>
        ) : null}

        {/* Right side: recommendation + toggle */}
        <div className="ml-auto flex items-center gap-2">
          {nextStepAction ? (
            <span className="max-w-[320px] truncate text-xs text-[var(--text-secondary)]">
              建议：{nextStepAction.title}
            </span>
          ) : null}
          <button
            type="button"
            onClick={() => setExpanded((prev) => !prev)}
            className="rounded-lg p-1 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-surface)]"
          >
            {expanded ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>

      {/* Expanded detail */}
      {expanded ? (
        <div className="mt-3 rounded-2xl border border-[var(--border-default)] bg-white/76 p-4">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            {currentPhaseTitle}
          </p>
          <p className="mt-2 text-xs leading-6 text-[var(--text-secondary)]">
            {headline ||
              currentPhaseDescription ||
              "直接描述你要推进的步骤，问津会通过对话确认后再决定是否开始执行。"}
          </p>
          <div className="mt-3 border-t border-[var(--border-default)] pt-3">
            <p className="text-xs font-medium text-[var(--text-primary)]">
              下一步建议
            </p>
            <p className="mt-1 text-xs leading-6 text-[var(--text-secondary)]">
              {nextStepAction?.reason ||
                nextStepAction?.description ||
                "直接描述你要推进的步骤，问津会通过对话确认后再决定是否开始执行。"}
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
