// frontend/components/workspace/AgentStatusBar.tsx

"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Check, Loader2, X, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useTaskStore } from "@/stores/task";

function StageNode({
  label,
  status,
}: {
  label: string;
  status: "completed" | "running" | "pending";
}) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className={cn(
          "w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium transition-all duration-300",
          status === "completed" && "bg-emerald-500 text-white",
          status === "running" &&
            "bg-[var(--accent-primary)] text-white shadow-lg shadow-[var(--accent-primary)]/30",
          status === "pending" &&
            "bg-[var(--bg-surface)] text-[var(--text-muted)] border border-[var(--border-default)]"
        )}
      >
        {status === "completed" && <Check className="w-4 h-4" />}
        {status === "running" && <Loader2 className="w-4 h-4 animate-spin" />}
        {status === "pending" && <span>○</span>}
      </div>
      <span
        className={cn(
          "text-[10px] whitespace-nowrap transition-colors",
          status === "completed" && "text-emerald-600",
          status === "running" && "text-[var(--accent-primary)] font-medium",
          status === "pending" && "text-[var(--text-muted)]"
        )}
      >
        {label}
      </span>
    </div>
  );
}

function StageConnector({ isCompleted }: { isCompleted: boolean }) {
  return (
    <div
      className={cn(
        "w-8 h-0.5 transition-colors duration-300",
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
        className="flex items-center gap-2 px-4 py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-600"
      >
        <Check className="w-5 h-5" />
        <span className="text-sm font-medium">任务完成！</span>
        <button
          onClick={clearRecentCompleted}
          className="ml-auto text-emerald-600/70 hover:text-emerald-600"
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

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)] overflow-hidden"
    >
      {/* 头部 */}
      <div
        className="flex items-center justify-between px-4 py-2 cursor-pointer hover:bg-[var(--bg-surface)] transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin text-[var(--accent-primary)]" />
          <span className="text-sm font-medium text-[var(--text-primary)]">
            {agentLabel} 正在工作...
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              cancelTask();
            }}
            className="text-xs text-[var(--text-muted)] hover:text-red-500 transition-colors px-2 py-1 rounded hover:bg-red-500/10"
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
            <div className="px-4 pb-3 pt-1">
              {/* 阶段进度 - 动态从stages渲染 */}
              {stages.length > 0 && (
                <div className="flex items-center justify-center gap-0 mb-3">
                  {stages.map((stage, index) => (
                    <div key={stage.id} className="flex items-center">
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
                <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-[var(--bg-surface)]">
                  <span className="text-[var(--accent-primary)]">💭</span>
                  <p className="text-xs text-[var(--text-secondary)] line-clamp-2">
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
