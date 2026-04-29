"use client";

import { Cpu, CheckCircle2, AlertCircle, Loader2, GitBranch } from "lucide-react";
import { cn } from "@/lib/utils";
import { statusLabel, formatShortId, sandboxStatusLabel, reviewStatusLabel, prismStatusLabel, reviewTone, prismTone } from "./utils";
import type { ComputeProjection, ExecutionSession } from "@/lib/api";

interface ComputeHeaderProps {
  effectiveExecution?: ExecutionSession | null;
  computeSession?: { id: string; execution_session_id: string } | null;
  projection?: ComputeProjection | null;
  isLoadingProjection?: boolean;
}

function SummaryItem({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "default" | "success" | "warning" | "danger";
}) {
  const toneClass = {
    default: "border-compute-border bg-compute-elevated text-compute-text-secondary",
    success: "border-compute-green/20 bg-compute-green/8 text-compute-green",
    warning: "border-compute-gold/20 bg-compute-gold/8 text-compute-gold",
    danger: "border-compute-red/20 bg-compute-red/8 text-compute-red",
  };
  return (
    <div
      className={cn(
        "rounded-xl border px-3 py-2",
        toneClass[tone ?? "default"]
      )}
    >
      <p className="text-[11px] text-compute-text-muted">{label}</p>
      <p className="mt-1 truncate text-sm font-medium text-compute-text-primary">
        {value}
      </p>
    </div>
  );
}

export function ComputeHeader({
  effectiveExecution,
  computeSession,
  projection,
  isLoadingProjection,
}: ComputeHeaderProps) {
  const sandbox = projection?.sandbox ?? null;
  const prism = projection?.prism ?? null;
  const reviewGate = projection?.review_gate ?? null;
  const files = projection?.files ?? sandbox?.files ?? [];
  const logs = projection?.logs ?? sandbox?.logs ?? [];
  const subagents = projection?.subagents ?? [];
  const nextActions = Array.isArray(reviewGate?.next_actions)
    ? reviewGate.next_actions
    : effectiveExecution?.next_actions ?? [];

  const status = effectiveExecution?.status;

  return (
    <div className="border-b border-compute-border px-4 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-compute-cyan" />
            <h3 className="truncate text-base font-semibold text-compute-text-primary">
              {effectiveExecution?.feature_id ?? "Compute Session"}
            </h3>
          </div>
          <p className="mt-1 text-xs text-compute-text-secondary">
            {computeSession
              ? `Compute ${formatShortId(computeSession.id)} · Execution ${formatShortId(computeSession.execution_session_id)}`
              : "等待 Compute session 绑定"}
          </p>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
            status === "completed"
              ? "border-compute-green/25 bg-compute-green/10 text-compute-green"
              : status === "failed"
                ? "border-compute-red/25 bg-compute-red/10 text-compute-red"
                : "border-compute-cyan/25 bg-compute-cyan/10 text-compute-cyan"
          )}
        >
          {status === "completed" ? (
            <CheckCircle2 className="h-3.5 w-3.5" />
          ) : status === "failed" ? (
            <AlertCircle className="h-3.5 w-3.5" />
          ) : isLoadingProjection ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <GitBranch className="h-3.5 w-3.5" />
          )}
          {statusLabel(status)}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <SummaryItem
          label="Task"
          value={formatShortId(effectiveExecution?.primary_task_id)}
        />
        <SummaryItem label="Subagents" value={String(subagents.length)} />
        <SummaryItem
          label="Sandbox"
          value={sandboxStatusLabel(sandbox?.status)}
          tone={
            sandbox?.status === "bound"
              ? "success"
              : sandbox?.required
                ? "warning"
                : "default"
          }
        />
        <SummaryItem
          label="Prism"
          value={prismStatusLabel(prism?.status)}
          tone={prismTone(prism)}
        />
        <SummaryItem label="Files" value={String(files.length)} />
        <SummaryItem label="Logs" value={String(logs.length)} />
        <SummaryItem
          label="Review"
          value={
            reviewGate
              ? reviewStatusLabel(reviewGate.status)
              : nextActions.length > 0
                ? `${nextActions.length} actions`
                : "None"
          }
          tone={reviewTone(reviewGate)}
        />
      </div>
    </div>
  );
}
