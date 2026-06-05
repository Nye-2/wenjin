"use client";

import { useState } from "react";
import { BookOpen, Loader2 } from "lucide-react";
import { importDeepSearchArtifactReferences } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ImportReferencesButtonProps {
  workspaceId: string;
  artifactIds: string[];
  source?: "deep_research" | "literature_search";
  label?: string;
  className?: string;
  disabled?: boolean;
  onImported?: (count: number) => Promise<void> | void;
  onError?: (message: string | null) => void;
  onSuccess?: (message: string | null) => void;
}

export function ImportReferencesButton({
  workspaceId,
  artifactIds,
  label = "同步到参考库",
  className,
  disabled = false,
  onImported,
  onError,
  onSuccess,
}: ImportReferencesButtonProps) {
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
      const response = await importDeepSearchArtifactReferences(workspaceId, {
        artifact_ids: artifactIds,
      });
      await onImported?.(response.imported);
      onSuccess?.(`已同步 ${response.imported} 条参考文献。`);
    } catch (error) {
      onError?.(error instanceof Error ? error.message : "参考文献同步失败");
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
        "inline-flex items-center gap-2 rounded-xl border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] px-3 py-2 text-[11px] font-medium text-[var(--wjn-text)] transition-colors hover:bg-[var(--bg-muted)] disabled:opacity-60",
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
