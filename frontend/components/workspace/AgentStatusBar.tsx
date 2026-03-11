// frontend/components/workspace/AgentStatusBar.tsx

"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Check, Loader2, X, ChevronDown, ChevronUp, Bot } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useTaskStore } from "@/stores/task";

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

export function AgentStatusBar() {
  const { currentTask, recentCompleted, cancelTask, clearRecentCompleted } =
    useTaskStore();
  const [isExpanded, setIsExpanded] = useState(true);

  // 完成状态提示
  if (recentCompleted) {
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
          <p className="text-xs text-emerald-600/70">{recentCompleted.agentLabel}</p>
        </div>
        <button
          onClick={clearRecentCompleted}
          className="p-1.5 rounded-lg text-emerald-600/70 hover:text-emerald-600 hover:bg-emerald-500/10 transition-colors"
          aria-label="关闭"
        >
          <X className="w-4 h-4" />
        </button>
      </motion.div>
    );
  }

  // 空闲状态
  if (!currentTask) {
    return null;
  }

  const { agentLabel, thinking, stages } = currentTask;
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
              cancelTask();
            }}
            className="text-xs text-[var(--text-muted)] hover:text-red-500 transition-colors px-2.5 py-1 rounded-lg hover:bg-red-500/10"
          >
            取消
          </button>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" />
          ) : (
            <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" />
          )}
        </div>
      </div>

      {/* 展开内容 */}
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
