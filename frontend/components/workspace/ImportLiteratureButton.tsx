"use client";

import { useState } from "react";
import { BookOpen, Loader2 } from "lucide-react";
import { importLiterature } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ImportLiteratureButtonProps {
  workspaceId: string;
  artifactIds: string[];
  source: "deep_research" | "literature_search";
  label?: string;
  className?: string;
  disabled?: boolean;
  onImported?: (count: number) => Promise<void> | void;
  onError?: (message: string | null) => void;
  onSuccess?: (message: string | null) => void;
}

export function ImportLiteratureButton({
  workspaceId,
  artifactIds,
  source,
  label = "导入到文献中心",
  className,
  disabled = false,
  onImported,
  onError,
  onSuccess,
}: ImportLiteratureButtonProps) {
  const [isImporting, setIsImporting] = useState(false);

  const handleClick = async () => {
    if (artifactIds.length === 0) {
      onError?.("当前没有可导入的参考文献候选。");
      return;
    }
    onError?.(null);
    onSuccess?.(null);
    setIsImporting(true);
    try {
      const response = await importLiterature(workspaceId, {
        source,
        artifact_ids: artifactIds,
      });
      await onImported?.(response.imported);
      onSuccess?.(`已导入 ${response.imported} 篇参考文献。`);
    } catch (error) {
      onError?.(error instanceof Error ? error.message : "文献导入失败");
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void handleClick()}
      disabled={disabled || isImporting}
      className={cn(
        "inline-flex items-center gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-[11px] font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-muted)] disabled:opacity-60",
        className
      )}
    >
      {isImporting ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <BookOpen className="h-3.5 w-3.5" />
      )}
      {label}
    </button>
  );
}
