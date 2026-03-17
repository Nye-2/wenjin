"use client";

import { AlertCircle, Loader2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

interface TaskFeedbackBannerProps {
  isRunning: boolean;
  status?: string | null;
  error?: string | null;
  onRetry?: () => void;
  className?: string;
  pendingText?: string;
}

export function TaskFeedbackBanner({
  isRunning,
  status,
  error,
  onRetry,
  className,
  pendingText = "任务执行中...",
}: TaskFeedbackBannerProps) {
  const message = error || status || (isRunning ? pendingText : null);
  if (!message) return null;

  if (error) {
    return (
      <div
        className={cn(
          "mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700",
          className
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{error}</span>
          </div>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex items-center gap-1 rounded border border-red-300 bg-white px-2 py-0.5 text-[11px] font-medium text-red-700 hover:bg-red-100"
            >
              <RefreshCw className="h-3 w-3" />
              重试
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "mt-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700",
        className
      )}
    >
      <div className="flex items-center gap-2">
        {isRunning && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        <span>{message}</span>
      </div>
    </div>
  );
}
