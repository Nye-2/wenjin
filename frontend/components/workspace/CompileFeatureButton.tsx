"use client";

import { useState } from "react";
import { Loader2, Play } from "lucide-react";
import { useFeaturesStore } from "@/stores/features";
import { useTaskStore } from "@/stores/task";
import { createWorkspaceFeatureTask, trackWorkspaceFeatureTask } from "@/lib/workspace-feature-execution";
import { cn } from "@/lib/utils";

interface CompileFeatureButtonProps {
  workspaceId: string;
  threadId?: string | null;
  featureId?: string;
  params?: Record<string, unknown>;
  label?: string;
  className?: string;
  disabled?: boolean;
  warningFallback?: string;
  missingTaskFallback?: string;
  onBeforeRun?: () => Promise<void> | void;
  onError?: (message: string | null) => void;
}

export function CompileFeatureButton({
  workspaceId,
  threadId,
  featureId = "compile_export",
  params = {},
  label = "一键编译",
  className,
  disabled = false,
  warningFallback = "编译暂时不可用",
  missingTaskFallback = "编译任务创建失败，请稍后重试",
  onBeforeRun,
  onError,
}: CompileFeatureButtonProps) {
  const { getFeatureById } = useFeaturesStore();
  const { startTask } = useTaskStore();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleClick = async () => {
    const feature = getFeatureById(featureId);
    if (!feature) {
      onError?.("当前工作区没有可用的编译能力。");
      return;
    }

    setIsSubmitting(true);
    onError?.(null);
    try {
      await onBeforeRun?.();
      const created = await createWorkspaceFeatureTask({
        workspaceId,
        featureId,
        params,
        threadId: threadId || undefined,
        warningFallback,
        missingTaskFallback,
      });
      trackWorkspaceFeatureTask({
        workspaceId,
        feature,
        startTask,
        taskId: created.taskId,
        initialThinking: created.message,
      });
    } catch (error) {
      onError?.(error instanceof Error ? error.message : "编译任务创建失败");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void handleClick()}
      disabled={disabled || isSubmitting}
      className={cn(
        "inline-flex items-center gap-2 rounded-xl bg-[var(--brand-navy)] px-3 py-2 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60",
        className
      )}
    >
      {isSubmitting ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <Play className="h-3.5 w-3.5" />
      )}
      {label}
    </button>
  );
}
