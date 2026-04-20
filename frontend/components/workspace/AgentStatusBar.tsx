// frontend/components/workspace/AgentStatusBar.tsx

"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  Bot,
  Check,
  ChevronDown,
  ChevronUp,
  Loader2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  cancelTask as cancelTaskRequest,
  getThreadState,
  type ExecutionSession,
  type PlatformThreadState,
  type ThreadRuntimeStatus,
} from "@/lib/api";
import { buildExecutionCurrentTask } from "@/lib/execution-presenters";
import { cn } from "@/lib/utils";
import { useThreadStore } from "@/stores/thread";
import { useExecutionStore } from "@/stores/execution";
import { useFeaturesStore } from "@/stores/features";

type StageStatus = "completed" | "running" | "pending";

interface StageNodeProps {
  label: string;
  status: StageStatus;
}

function StageNode({ label, status }: StageNodeProps) {
  const statusStyles: Record<StageStatus, string> = {
    completed: "bg-emerald-500 text-white",
    running:
      "bg-[var(--accent-primary)] text-white shadow-lg shadow-[var(--accent-primary)]/30",
    pending:
      "bg-[var(--bg-surface)] text-[var(--text-muted)] border border-[var(--border-default)]",
  };

  const labelStyles: Record<StageStatus, string> = {
    completed: "text-emerald-600",
    running: "text-[var(--accent-primary)] font-medium",
    pending: "text-[var(--text-muted)]",
  };

  return (
    <div className="flex flex-col items-center gap-1.5">
      <div
        className={cn(
          "w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium transition-all duration-300",
          statusStyles[status]
        )}
      >
        {status === "completed" && <Check className="w-3.5 h-3.5" />}
        {status === "running" && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
        {status === "pending" && <span className="text-[10px]">○</span>}
      </div>
      <span
        className={cn(
          "text-[10px] whitespace-nowrap transition-colors",
          labelStyles[status]
        )}
      >
        {label}
      </span>
    </div>
  );
}

interface StageConnectorProps {
  isCompleted: boolean;
}

function StageConnector({ isCompleted }: StageConnectorProps) {
  return (
    <div
      className={cn(
        "w-6 h-0.5 mx-1 transition-colors duration-300",
        isCompleted ? "bg-emerald-500" : "bg-[var(--border-default)]"
      )}
    />
  );
}

interface AgentStatusBarProps {
  workspaceId: string;
}
const EMPTY_EXECUTION_SESSIONS: ExecutionSession[] = [];

function toThreadRuntimeStatus(
  threadId: string,
  state: PlatformThreadState
): ThreadRuntimeStatus {
  const metadata =
    state && typeof state.metadata === "object" && state.metadata
      ? state.metadata
      : {};
  const rawStatus =
    typeof metadata.status === "string" ? metadata.status.trim() : "idle";
  const activeTaskCount = Array.isArray(state.tasks) ? state.tasks.length : 0;

  let status: ThreadRuntimeStatus["status"] = "idle";
  if (activeTaskCount > 0 || rawStatus === "busy" || rawStatus === "running") {
    status = "running";
  } else if (
    rawStatus === "failed" ||
    rawStatus === "error" ||
    rawStatus === "interrupted"
  ) {
    status = "failed";
  } else if (rawStatus === "completed" || rawStatus === "success") {
    status = "completed";
  }

  return {
    thread_id: threadId,
    status,
    current_skill:
      typeof metadata.skill === "string" ? metadata.skill : null,
    current_skill_name:
      typeof metadata.skill_name === "string" ? metadata.skill_name : null,
    subagent_count: activeTaskCount,
  };
}

export function AgentStatusBar({ workspaceId }: AgentStatusBarProps) {
  const threadId = useThreadStore((state) => state.threadId);
  const activeSkill = useThreadStore((state) => state.activeSkill);
  const isStreaming = useThreadStore((state) => state.isStreaming);
  const currentThreadSummary = useThreadStore(
    (state) => state.currentThreadSummary
  );
  const threadStatuses = useThreadStore((state) => state.threadStatuses);
  const setThreadStatus = useThreadStore((state) => state.setThreadStatus);
  const executionSessions = useExecutionStore(
    (state) => state.byWorkspace[workspaceId] ?? EMPTY_EXECUTION_SESSIONS
  );
  const getSkillById = useFeaturesStore((state) => state.getSkillById);
  const getFeatureById = useFeaturesStore((state) => state.getFeatureById);
  const [isExpanded, setIsExpanded] = useState(true);
  const [isCancelling, setIsCancelling] = useState(false);
  const [taskActionError, setTaskActionError] = useState<string | null>(null);
  const [dismissedFailureExecutionId, setDismissedFailureExecutionId] = useState<string | null>(null);
  const [dismissedCompletedExecutionId, setDismissedCompletedExecutionId] = useState<string | null>(null);
  const threadStatus: ThreadRuntimeStatus | null = threadId ? threadStatuses[threadId] ?? null : null;
  const sortedExecutions = useMemo(
    () =>
      [...executionSessions].sort((left, right) =>
        String(right.updated_at || right.created_at || "").localeCompare(
          String(left.updated_at || left.created_at || "")
        )
      ),
    [executionSessions]
  );
  const activeExecution =
    sortedExecutions.find(
      (execution) =>
        execution.status === "running" ||
        execution.status === "pending" ||
        execution.status === "awaiting_user_input"
    ) ?? null;
  const latestFailedExecution =
    sortedExecutions.find(
      (execution) =>
        execution.status === "failed" || execution.status === "advisory"
    ) ?? null;
  const latestCompletedExecution =
    sortedExecutions.find((execution) => execution.status === "completed") ?? null;
  const effectiveCurrentTask =
    activeExecution
      ? buildExecutionCurrentTask(
          activeExecution,
          getFeatureById(activeExecution.feature_id)
        )
      : latestFailedExecution &&
          dismissedFailureExecutionId !== latestFailedExecution.id
        ? buildExecutionCurrentTask(
            latestFailedExecution,
            getFeatureById(latestFailedExecution.feature_id)
          )
        : null;
  const effectiveRecentCompleted =
    latestCompletedExecution &&
    dismissedCompletedExecutionId !== latestCompletedExecution.id &&
    Date.now() -
      new Date(
        latestCompletedExecution.completed_at ||
          latestCompletedExecution.updated_at ||
          latestCompletedExecution.created_at ||
          0
      ).getTime() <
      2 * 60 * 1000
      ? buildExecutionCurrentTask(
          latestCompletedExecution,
          getFeatureById(latestCompletedExecution.feature_id)
        )
      : null;

  useEffect(() => {
    if (!threadId || threadStatus) {
      return;
    }

    let cancelled = false;

    const loadStatus = async () => {
      try {
        const state = await getThreadState(threadId);
        if (!cancelled) {
          setThreadStatus(toThreadRuntimeStatus(threadId, state));
        }
      } catch {
        // Ignore transient load errors; live workspace events will retry naturally.
      }
    };

    void loadStatus();

    return () => {
      cancelled = true;
    };
  }, [threadId, threadStatus, setThreadStatus]);

  useEffect(() => {
    setTaskActionError(null);
    setIsCancelling(false);
  }, [effectiveCurrentTask?.id, effectiveCurrentTask?.status]);

  useEffect(() => {
    if (!latestFailedExecution || latestFailedExecution.id !== dismissedFailureExecutionId) {
      setDismissedFailureExecutionId(null);
    }
  }, [latestFailedExecution, dismissedFailureExecutionId]);

  useEffect(() => {
    if (!latestCompletedExecution) {
      setDismissedCompletedExecutionId(null);
    }
  }, [latestCompletedExecution]);

  const handleDismissFailedTask = () => {
    setTaskActionError(null);
    setDismissedFailureExecutionId(latestFailedExecution?.id ?? null);
  };

  const handleCancelCurrentTask = async () => {
    if (!effectiveCurrentTask || effectiveCurrentTask.status !== "running" || isCancelling) {
      return;
    }

    setTaskActionError(null);
    setIsCancelling(true);
    try {
      await cancelTaskRequest(effectiveCurrentTask.id);
    } catch (error) {
      setTaskActionError(
        error instanceof Error ? error.message : "取消任务失败，请稍后重试"
      );
    } finally {
      setIsCancelling(false);
    }
  };

  if (effectiveCurrentTask?.status === "failed") {
    const failureMessage = effectiveCurrentTask.thinking.replace(/^错误:\s*/, "").trim();
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3"
      >
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-red-500/15">
            <AlertCircle className="h-4 w-4 text-red-500" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-red-700">任务失败</p>
            <p className="text-xs text-red-600/80">{effectiveCurrentTask.agentLabel}</p>
            <p className="mt-1 text-xs leading-5 text-red-700/90">
              {failureMessage || "任务执行失败，请稍后重试。"}
            </p>
          </div>
          <button
            onClick={handleDismissFailedTask}
            className="rounded-lg p-1.5 text-red-600/70 transition-colors hover:bg-red-500/10 hover:text-red-600"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </motion.div>
    );
  }

  // 完成状态提示
  if (effectiveRecentCompleted) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        className="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20"
      >
        <div className="w-6 h-6 rounded-full bg-emerald-500 flex items-center justify-center">
          <Check className="w-4 h-4 text-white" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-emerald-700">任务完成</p>
          <p className="text-xs text-emerald-600/70">{effectiveRecentCompleted.agentLabel}</p>
        </div>
        <button
          onClick={() =>
            setDismissedCompletedExecutionId(latestCompletedExecution?.id ?? null)
          }
          className="p-1.5 rounded-lg text-emerald-600/70 hover:text-emerald-600 hover:bg-emerald-500/10 transition-colors"
          aria-label="关闭"
        >
          <X className="w-4 h-4" />
        </button>
      </motion.div>
    );
  }

  // 空闲状态
  if (!effectiveCurrentTask) {
    const visibleThreadStatus = threadId ? threadStatus : null;
    const effectiveStatus =
      isStreaming
        ? "running"
        : visibleThreadStatus?.status && visibleThreadStatus.status !== "idle"
          ? visibleThreadStatus.status
          : null;
    if (!effectiveStatus) {
      return null;
    }

    const effectiveSkillId = visibleThreadStatus?.current_skill || activeSkill;
    const skillLabel = effectiveSkillId
      ? (
          visibleThreadStatus?.current_skill_name ||
          (currentThreadSummary?.skill === effectiveSkillId
            ? currentThreadSummary.skill_name
            : null) ||
          getSkillById(effectiveSkillId)?.name ||
          effectiveSkillId
        )
      : "thread";

    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        className="rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)] px-4 py-3"
      >
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg bg-[var(--accent-primary)]/10 flex items-center justify-center">
            {effectiveStatus === "running" ? (
              <Loader2 className="w-4 h-4 animate-spin text-[var(--accent-primary)]" />
            ) : effectiveStatus === "completed" ? (
              <Check className="w-4 h-4 text-emerald-500" />
            ) : (
              <Bot className="w-4 h-4 text-red-500" />
            )}
          </div>
          <div className="flex-1">
            <p className="text-sm font-medium text-[var(--text-primary)]">
              {skillLabel}
            </p>
            <p className="text-xs text-[var(--text-muted)]">
              {effectiveStatus === "running"
                ? "对话处理中"
                : effectiveStatus === "completed"
                  ? "对话已完成"
                  : "对话执行失败"}
              {(visibleThreadStatus?.subagent_count ?? 0) > 0
                ? ` · ${visibleThreadStatus?.subagent_count} 个子代理`
                : ""}
            </p>
          </div>
        </div>
      </motion.div>
    );
  }

  const { agentLabel, thinking, stages } = effectiveCurrentTask;
  const completedCount = stages.filter((s) => s.status === "completed").length;
  const progress = stages.length > 0 ? (completedCount / stages.length) * 100 : 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)] overflow-hidden"
    >
      {/* 头部 */}
      <div
        className="flex items-center justify-between px-4 py-2.5 cursor-pointer hover:bg-[var(--bg-surface)]/50 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg bg-[var(--accent-primary)]/10 flex items-center justify-center">
            <Bot className="w-4 h-4 text-[var(--accent-primary)]" />
          </div>
          <div>
            <p className="text-sm font-medium text-[var(--text-primary)]">
              {agentLabel}
            </p>
            <p className="text-xs text-[var(--text-muted)]">
              {completedCount}/{stages.length} 阶段完成
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* 进度条 */}
          <div className="hidden sm:flex w-20 h-1.5 bg-[var(--bg-surface)] rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-[var(--accent-primary)]"
              initial={{ width: 0 }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              void handleCancelCurrentTask();
            }}
            disabled={isCancelling}
            className="text-xs text-[var(--text-muted)] hover:text-red-500 transition-colors px-2.5 py-1 rounded-lg hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isCancelling ? "取消中..." : "取消"}
          </button>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" />
          ) : (
            <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" />
          )}
        </div>
      </div>

      {/* 展开内容 */}
      {taskActionError && (
        <div className="mx-4 mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-700">
          {taskActionError}
        </div>
      )}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-3 pt-1 border-t border-[var(--border-default)]/50">
              {/* 阶段进度 */}
              {stages.length > 0 && (
                <div className="flex items-center justify-center py-3 mb-2 overflow-x-auto">
                  {stages.map((stage, index) => (
                    <div key={stage.id} className="flex items-center shrink-0">
                      <StageNode label={stage.label} status={stage.status} />
                      {index < stages.length - 1 && (
                        <StageConnector isCompleted={stage.status === "completed"} />
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* 思考气泡 */}
              {thinking && (
                <div className="flex items-start gap-2.5 px-3 py-2.5 rounded-lg bg-[var(--bg-surface)]">
                  <span className="text-base">💭</span>
                  <p className="text-xs text-[var(--text-secondary)] line-clamp-2 flex-1">
                    {thinking}
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
