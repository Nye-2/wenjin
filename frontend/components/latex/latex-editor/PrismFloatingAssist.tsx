"use client";

import { MessageSquareText, Sparkles, Users } from "lucide-react";

import { Button } from "@/components/ui/button";

export function PrismFloatingAssist({
  isPanelOpen,
  selectedCharacterCount,
  pendingRewriteCount,
  runningJobCount,
  hasError,
  onOpen,
  onAnnotate,
  onQuickRewrite,
  onDeepAssist,
}: {
  isPanelOpen: boolean;
  selectedCharacterCount: number;
  pendingRewriteCount: number;
  runningJobCount: number;
  hasError: boolean;
  onOpen: () => void;
  onAnnotate: () => void;
  onQuickRewrite: () => void;
  onDeepAssist: () => void;
}) {
  if (isPanelOpen) {
    return null;
  }

  const pillLabel = hasError
    ? "需要处理"
    : pendingRewriteCount > 0
      ? "待应用修改"
      : runningJobCount > 0
        ? "团队处理中"
        : selectedCharacterCount > 0
          ? `已选 ${selectedCharacterCount} 字`
          : "AI 改稿";

  return (
    <div className="pointer-events-none fixed bottom-5 right-5 z-40 flex flex-col items-end gap-2">
      {selectedCharacterCount > 0 ? (
        <div className="pointer-events-auto flex items-center gap-1 rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white/95 p-1 shadow-[var(--wjn-shadow-lg)] backdrop-blur">
          <Button size="sm" variant="outline" onClick={onAnnotate}>
            <MessageSquareText className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            批注
          </Button>
          <Button size="sm" onClick={onQuickRewrite}>
            <Sparkles className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            改这段
          </Button>
          <Button size="sm" variant="outline" onClick={onDeepAssist}>
            <Users className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            修改全文
          </Button>
        </div>
      ) : null}
      <button
        type="button"
        onClick={onOpen}
        className={[
          "pointer-events-auto inline-flex h-10 items-center gap-2 rounded-full border px-4 text-sm font-semibold shadow-[var(--wjn-shadow-lg)] backdrop-blur transition-colors",
          hasError
            ? "border-red-200 bg-red-50 text-red-700"
            : pendingRewriteCount > 0 || runningJobCount > 0
              ? "border-[var(--wjn-accent-line)] bg-[var(--wjn-accent-soft)] text-[var(--wjn-accent-strong)]"
              : "border-[var(--wjn-line)] bg-white/95 text-[var(--wjn-text)] hover:border-[var(--wjn-accent-line)]",
        ].join(" ")}
        aria-label={pillLabel}
        title={pillLabel}
      >
        <Sparkles className="h-4 w-4" aria-hidden="true" />
        {pillLabel}
      </button>
    </div>
  );
}
