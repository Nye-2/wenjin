"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Loader2,
  CheckCircle2,
  AlertCircle,
  Clock3,
  ChevronDown,
  ChevronUp,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/*  Types                                                                      */
/* -------------------------------------------------------------------------- */

type TaskCardStatus = "pending" | "running" | "success" | "failed" | "cancelled";

interface TaskCardProps {
  taskId: string;
  taskType: string;
  status: TaskCardStatus;
  progress: number;
  message: string | null;
  featureName?: string;
  result?: Record<string, unknown> | null;
  error?: string | null;
  onViewDetail?: () => void;
  className?: string;
}

/* -------------------------------------------------------------------------- */
/*  Status visual mapping                                                      */
/* -------------------------------------------------------------------------- */

interface StatusVisual {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  borderColor: string;
  background: string;
  iconColor: string;
}

const STATUS_MAP: Record<TaskCardStatus, StatusVisual> = {
  pending: {
    icon: Clock3,
    label: "Queued",
    borderColor: "border-slate-300",
    background: "bg-slate-50",
    iconColor: "text-slate-500",
  },
  running: {
    icon: Loader2,
    label: "Running",
    borderColor: "border-amber-300",
    background: "bg-amber-50",
    iconColor: "text-amber-500",
  },
  success: {
    icon: CheckCircle2,
    label: "Completed",
    borderColor: "border-emerald-300",
    background: "bg-emerald-50",
    iconColor: "text-emerald-500",
  },
  failed: {
    icon: AlertCircle,
    label: "Failed",
    borderColor: "border-red-300",
    background: "bg-red-50",
    iconColor: "text-red-500",
  },
  cancelled: {
    icon: AlertCircle,
    label: "Cancelled",
    borderColor: "border-slate-300",
    background: "bg-slate-50",
    iconColor: "text-slate-400",
  },
};

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                    */
/* -------------------------------------------------------------------------- */

/** Convert a snake_case / kebab-case taskType to a readable display name. */
function formatTaskType(raw: string): string {
  return raw
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Whether the task is in a terminal state (can expand details). */
function isTerminal(status: TaskCardStatus): boolean {
  return status === "success" || status === "failed" || status === "cancelled";
}

/* -------------------------------------------------------------------------- */
/*  Component                                                                  */
/* -------------------------------------------------------------------------- */

export function TaskCard({
  taskId,
  taskType,
  status,
  progress,
  message,
  featureName,
  result,
  error,
  onViewDetail,
  className,
}: TaskCardProps) {
  const [expanded, setExpanded] = useState(false);

  const visual = STATUS_MAP[status];
  const StatusIcon = visual.icon;
  const displayName = featureName || formatTaskType(taskType);
  const hasExpandableContent =
    isTerminal(status) && (!!error || (!!result && Object.keys(result).length > 0));

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "rounded-xl border overflow-hidden",
        visual.borderColor,
        visual.background,
        className
      )}
      data-task-id={taskId}
    >
      {/* ---- Header row -------------------------------------------------- */}
      <div className="flex items-center gap-2.5 px-4 py-3">
        <StatusIcon
          className={cn(
            "h-4 w-4 shrink-0",
            visual.iconColor,
            status === "running" && "animate-spin"
          )}
        />

        <span className="min-w-0 flex-1 truncate text-sm font-medium text-[var(--text-primary)]">
          {displayName}
        </span>

        <span
          className={cn(
            "shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium",
            visual.iconColor,
            status === "pending" && "bg-slate-200/60",
            status === "running" && "bg-amber-200/60",
            status === "success" && "bg-emerald-200/60",
            status === "failed" && "bg-red-200/60",
            status === "cancelled" && "bg-slate-200/60"
          )}
        >
          {visual.label}
        </span>

        {onViewDetail && (
          <button
            type="button"
            onClick={onViewDetail}
            className="shrink-0 rounded-lg p-1 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)]"
            aria-label="View detail"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* ---- Message subtitle -------------------------------------------- */}
      {message && (
        <p className="truncate px-4 pb-2 text-xs leading-5 text-[var(--text-muted)]">
          {message}
        </p>
      )}

      {/* ---- Progress bar (running only) --------------------------------- */}
      {status === "running" && (
        <div className="mx-4 mb-3 h-1.5 overflow-hidden rounded-full bg-amber-200/50">
          <motion.div
            className="h-full rounded-full bg-amber-500"
            initial={{ width: 0 }}
            animate={{ width: `${Math.min(Math.max(progress, 0), 100)}%` }}
            transition={{ duration: 0.4, ease: "easeOut" }}
          />
        </div>
      )}

      {/* ---- Expandable detail toggle ------------------------------------ */}
      {hasExpandableContent && (
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          className={cn(
            "flex w-full items-center justify-center gap-1 border-t px-4 py-1.5 text-[11px] font-medium transition-colors",
            "text-[var(--text-muted)] hover:bg-[var(--bg-muted)]/40",
            visual.borderColor
          )}
        >
          {expanded ? "Hide details" : "Show details"}
          {expanded ? (
            <ChevronUp className="h-3 w-3" />
          ) : (
            <ChevronDown className="h-3 w-3" />
          )}
        </button>
      )}

      {/* ---- Expandable content ------------------------------------------ */}
      <AnimatePresence>
        {expanded && hasExpandableContent && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="border-t px-4 py-3" style={{ borderColor: "inherit" }}>
              {error && (
                <div className="rounded-lg bg-red-100 px-3 py-2 text-xs leading-5 text-red-700">
                  {error}
                </div>
              )}

              {result && !error && (
                <pre className="max-h-40 overflow-auto rounded-lg bg-[var(--bg-muted)] px-3 py-2 text-[11px] leading-5 text-[var(--text-secondary)]">
                  {JSON.stringify(result, null, 2)}
                </pre>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export type { TaskCardStatus, TaskCardProps };
