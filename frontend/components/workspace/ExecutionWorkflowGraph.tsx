"use client";

import { Bot, GitBranch } from "lucide-react";
import { useMemo } from "react";
import type { ExecutionPanelSubagent } from "@/lib/execution-presenters";
import { cn } from "@/lib/utils";

interface ExecutionWorkflowGraphProps {
  items: ExecutionPanelSubagent[];
  className?: string;
  selectedPhaseKey?: string | null;
  selectedSubagentId?: string | null;
  onSelectPhase?: (selection: { key: string; label: string } | null) => void;
  onSelectSubagent?: (selection: { id: string; phaseKey: string } | null) => void;
}

type NodeStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

interface WorkflowPhaseNode {
  key: string;
  label: string;
  index: number | null;
  status: NodeStatus;
  items: ExecutionPanelSubagent[];
}

interface WorkflowPhaseIdentity {
  key: string;
  label: string;
  index: number | null;
}

function normalizeStatus(status: string): NodeStatus {
  switch (status) {
    case "completed":
    case "success":
      return "completed";
    case "failed":
    case "error":
      return "failed";
    case "cancelled":
      return "cancelled";
    case "running":
      return "running";
    default:
      return "pending";
  }
}

function formatStatusLabel(status: NodeStatus): string {
  switch (status) {
    case "completed":
      return "完成";
    case "failed":
      return "失败";
    case "cancelled":
      return "已取消";
    case "running":
      return "进行中";
    default:
      return "等待中";
  }
}

function nodeStatusStyles(status: NodeStatus): string {
  switch (status) {
    case "completed":
      return "bg-emerald-500/12 text-emerald-700 border-emerald-500/25";
    case "failed":
      return "bg-red-500/10 text-red-700 border-red-500/20";
    case "cancelled":
      return "bg-slate-500/12 text-slate-700 border-slate-500/20";
    case "running":
      return "bg-[var(--accent-primary)]/12 text-[var(--accent-primary)] border-[var(--accent-primary)]/20";
    default:
      return "bg-white/70 text-[var(--text-secondary)] border-[var(--border-default)]";
  }
}

function normalizePhaseLabel(value: string | null): string {
  if (!value) {
    return "执行阶段";
  }
  return value
    .replace(/_/g, " ")
    .split(" ")
    .filter(Boolean)
    .join(" ");
}

export function buildWorkflowPhaseIdentity(
  item: Pick<ExecutionPanelSubagent, "workflowPhase" | "workflowPhaseIndex">
): WorkflowPhaseIdentity {
  const label = normalizePhaseLabel(item.workflowPhase);
  const index =
    typeof item.workflowPhaseIndex === "number" &&
    Number.isFinite(item.workflowPhaseIndex)
      ? item.workflowPhaseIndex
      : null;
  return {
    key: `${index ?? "na"}:${label.toLowerCase()}`,
    label,
    index,
  };
}

function derivePhaseStatus(items: ExecutionPanelSubagent[]): NodeStatus {
  const statuses = items.map((item) => normalizeStatus(item.status));
  if (statuses.some((status) => status === "failed")) {
    return "failed";
  }
  if (statuses.some((status) => status === "running")) {
    return "running";
  }
  if (
    statuses.length > 0 &&
    statuses.every((status) => status === "completed")
  ) {
    return "completed";
  }
  if (
    statuses.length > 0 &&
    statuses.every((status) => status === "cancelled")
  ) {
    return "cancelled";
  }
  return "pending";
}

function buildWorkflowPhases(items: ExecutionPanelSubagent[]): WorkflowPhaseNode[] {
  const phaseMap = new Map<string, WorkflowPhaseNode>();

  for (const item of items) {
    const phaseIdentity = buildWorkflowPhaseIdentity(item);
    const phaseKey = phaseIdentity.key;
    const existing = phaseMap.get(phaseKey);
    if (existing) {
      existing.items.push(item);
      if (
        existing.index === null &&
        phaseIdentity.index !== null
      ) {
        existing.index = phaseIdentity.index;
      }
      continue;
    }
    phaseMap.set(phaseKey, {
      key: phaseKey,
      label: phaseIdentity.label,
      index: phaseIdentity.index,
      status: "pending",
      items: [item],
    });
  }

  const phases = Array.from(phaseMap.values());
  for (const phase of phases) {
    phase.items.sort((left, right) => {
      const leftTaskIndex =
        typeof left.workflowTaskIndex === "number" && Number.isFinite(left.workflowTaskIndex)
          ? left.workflowTaskIndex
          : Number.MAX_SAFE_INTEGER;
      const rightTaskIndex =
        typeof right.workflowTaskIndex === "number" && Number.isFinite(right.workflowTaskIndex)
          ? right.workflowTaskIndex
          : Number.MAX_SAFE_INTEGER;
      if (leftTaskIndex !== rightTaskIndex) {
        return leftTaskIndex - rightTaskIndex;
      }
      return right.updatedAt.localeCompare(left.updatedAt);
    });
    phase.status = derivePhaseStatus(phase.items);
  }

  phases.sort((left, right) => {
    const leftIndex = left.index ?? Number.MAX_SAFE_INTEGER;
    const rightIndex = right.index ?? Number.MAX_SAFE_INTEGER;
    if (leftIndex !== rightIndex) {
      return leftIndex - rightIndex;
    }
    return left.label.localeCompare(right.label, "zh-CN");
  });
  return phases;
}

function previewText(item: ExecutionPanelSubagent): string {
  const raw =
    item.error ||
    item.outputPreview ||
    "等待该子任务返回摘要或中间结果。";
  if (raw.length <= 120) {
    return raw;
  }
  return `${raw.slice(0, 120)}…`;
}

export function ExecutionWorkflowGraph({
  items,
  className,
  selectedPhaseKey = null,
  selectedSubagentId = null,
  onSelectPhase,
  onSelectSubagent,
}: ExecutionWorkflowGraphProps) {
  const phases = useMemo(() => buildWorkflowPhases(items), [items]);
  const phaseNumberOffset = useMemo(
    () => (phases.some((phase) => phase.index === 0) ? 1 : 0),
    [phases]
  );
  const strategies = useMemo(
    () =>
      Array.from(
        new Set(
          items
            .map((item) => item.workflowStrategy?.trim() || "")
            .filter((value) => value.length > 0)
        )
      ),
    [items]
  );

  if (items.length === 0) {
    return null;
  }

  return (
    <section
      className={cn(
        "rounded-2xl border border-[var(--border-default)] bg-white/76 p-4",
        className
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-[var(--brand-teal)]" />
            <h4 className="text-sm font-medium text-[var(--text-primary)]">
              LangGraph 执行图
            </h4>
          </div>
          <p className="mt-1 text-[11px] leading-5 text-[var(--text-muted)]">
            Leader 动态编排 subagents，按 phase/task 推进执行链路。
          </p>
        </div>
        <span className="rounded-full border border-[var(--border-default)] bg-white/80 px-2.5 py-1 text-[10px] text-[var(--text-muted)]">
          {phases.length} phases
        </span>
      </div>

      {strategies.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {strategies.slice(0, 4).map((strategy) => (
            <span
              key={strategy}
              className="rounded-full border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2.5 py-1 text-[10px] text-[var(--text-secondary)]"
            >
              strategy: {strategy}
            </span>
          ))}
        </div>
      ) : null}

      <div className="mt-4 space-y-3">
        {phases.map((phase, index) => (
          <div key={phase.key} className="relative pl-9">
            {index < phases.length - 1 ? (
              <span className="absolute left-[13px] top-8 h-[calc(100%-1.75rem)] w-px bg-[var(--border-default)]" />
            ) : null}

            <div
              className={cn(
                "absolute left-0 top-1 inline-flex h-7 w-7 items-center justify-center rounded-full border text-[11px] font-medium",
                nodeStatusStyles(phase.status)
              )}
            >
              {phase.index !== null ? phase.index + phaseNumberOffset : index + 1}
            </div>

            <div
              className={cn(
                "rounded-xl border bg-[var(--bg-elevated)] px-3 py-3",
                selectedPhaseKey === phase.key
                  ? "border-[var(--accent-primary)]/35 ring-1 ring-[var(--accent-primary)]/20"
                  : "border-[var(--border-default)]"
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={() =>
                    onSelectPhase?.(
                      selectedPhaseKey === phase.key
                        ? null
                        : { key: phase.key, label: phase.label }
                    )
                  }
                  className={cn(
                    "text-left text-xs font-medium transition-colors",
                    selectedPhaseKey === phase.key
                      ? "text-[var(--accent-primary)]"
                      : "text-[var(--text-primary)] hover:text-[var(--accent-primary)]"
                  )}
                >
                  {phase.label}
                </button>
                <span
                  className={cn(
                    "rounded-full border px-2 py-0.5 text-[10px]",
                    nodeStatusStyles(phase.status)
                  )}
                >
                  {formatStatusLabel(phase.status)}
                </span>
              </div>
              <p className="mt-1 text-[10px] text-[var(--text-muted)]">
                {phase.items.length} 个子任务
              </p>

              <div className="mt-2 space-y-2">
                {phase.items.map((item) => {
                  const itemStatus = normalizeStatus(item.status);
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() =>
                        onSelectSubagent?.(
                          selectedSubagentId === item.id
                            ? null
                            : { id: item.id, phaseKey: phase.key }
                        )
                      }
                      className={cn(
                        "w-full rounded-lg border bg-white/85 px-2.5 py-2 text-left transition-colors",
                        selectedSubagentId === item.id
                          ? "border-[var(--accent-primary)]/35 ring-1 ring-[var(--accent-primary)]/20"
                          : "border-[var(--border-default)] hover:border-[var(--accent-primary)]/25"
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-[11px] font-medium text-[var(--text-primary)]">
                          {item.subagentType?.replace(/_/g, " ") || "subagent"}
                        </p>
                        <span
                          className={cn(
                            "rounded-full border px-2 py-0.5 text-[10px]",
                            nodeStatusStyles(itemStatus)
                          )}
                        >
                          {formatStatusLabel(itemStatus)}
                        </span>
                      </div>
                      <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                        {previewText(item)}
                      </p>
                      <div className="mt-1.5 flex items-center justify-between gap-2 text-[10px] text-[var(--text-muted)]">
                        <span className="inline-flex items-center gap-1">
                          <Bot className="h-3 w-3" />
                          {item.id.slice(0, 8)}
                        </span>
                        <span>
                          {new Date(item.updatedAt).toLocaleTimeString("zh-CN", {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
