"use client";

import { useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

interface SaveArtifactButtonProps {
  label?: string;
  className?: string;
  disabled?: boolean;
  onSave: () => Promise<void> | void;
  onError?: (message: string | null) => void;
}

export function SaveArtifactButton({
  label = "保存",
  className,
  disabled = false,
  onSave,
  onError,
}: SaveArtifactButtonProps) {
  const [isSaving, setIsSaving] = useState(false);

  const handleClick = async () => {
    onError?.(null);
    setIsSaving(true);
    try {
      await onSave();
    } catch (error) {
      onError?.(error instanceof Error ? error.message : "保存失败");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void handleClick()}
      disabled={disabled || isSaving}
      className={cn(
        "inline-flex items-center gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-xs font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-muted)] disabled:opacity-60",
        className
      )}
    >
      {isSaving ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <RefreshCw className="h-3.5 w-3.5" />
      )}
      {label}
    </button>
  );
}
