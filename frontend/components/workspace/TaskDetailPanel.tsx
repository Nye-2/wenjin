"use client";

import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import type { TaskRuntimeState } from "@/lib/task-runtime";
import { TaskRuntimePanel } from "@/components/workspace/TaskRuntimePanel";

interface TaskDetailPanelProps {
  open: boolean;
  onClose: () => void;
  taskId: string | null;
  runtime: TaskRuntimeState | null;
  status: string | null;
  error: string | null;
  title?: string;
}

const RUNNING_STATUSES = new Set(["running", "pending", "in_progress"]);

export function TaskDetailPanel({
  open,
  onClose,
  taskId,
  runtime,
  status,
  error,
  title,
}: TaskDetailPanelProps) {
  const isRunning = !!status && RUNNING_STATUSES.has(status);

  return (
    <AnimatePresence mode="wait">
      {open && (
        <motion.div
          key="task-detail-panel"
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 380, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          className="shrink-0 overflow-hidden border-l border-[var(--border-default)] bg-[var(--bg-surface)]"
        >
          <div className="flex h-full w-[380px] flex-col">
            {/* Header */}
            <div className="flex items-center justify-between gap-3 border-b border-[var(--border-default)] px-4 py-3">
              <div className="min-w-0">
                <h2 className="truncate text-sm font-semibold text-[var(--text-primary)]">
                  {title || "Task Details"}
                </h2>
                {taskId && (
                  <p className="mt-0.5 truncate text-xs text-[var(--text-muted)]">
                    {taskId}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={onClose}
                className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]"
                aria-label="Close detail panel"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4">
              <TaskRuntimePanel
                runtime={runtime}
                isRunning={isRunning}
                status={status}
                error={error}
                title={title}
              />
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
