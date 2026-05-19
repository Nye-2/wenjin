"use client";

import { AlertTriangle, FileText, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

type WorkspaceSurfaceStateTone = "loading" | "error" | "empty";

type WorkspaceSurfaceStateProps = {
  tone: WorkspaceSurfaceStateTone;
  title: string;
  description?: string | null;
  className?: string;
  testId?: string;
};

export function WorkspaceSurfaceState({
  tone,
  title,
  description,
  className,
  testId = "workspace-surface-state",
}: WorkspaceSurfaceStateProps) {
  const Icon =
    tone === "loading" ? Loader2 : tone === "error" ? AlertTriangle : FileText;

  return (
    <div
      className={cn(
        "flex h-full min-h-[420px] items-center justify-center px-4 py-8 sm:px-6",
        className,
      )}
      style={{ background: "var(--v2-bg-gradient)" }}
    >
      <div
        data-testid={testId}
        className={cn(
          "w-full max-w-md rounded-[var(--v2-radius-lg)] border px-5 py-5 text-center shadow-[var(--v2-glass-shadow)] backdrop-blur-xl",
          tone === "error"
            ? "border-red-500/20 bg-white/80"
            : "border-[var(--v2-glass-border)] bg-[var(--v2-glass-bg-elevated)]",
        )}
      >
        <div
          className={cn(
            "mx-auto flex h-10 w-10 items-center justify-center rounded-full",
            tone === "error"
              ? "bg-red-500/10 text-red-700"
              : "bg-[var(--v2-accent-purple-100)] text-[var(--v2-accent-purple-700)]",
          )}
        >
          <Icon
            className={cn("h-5 w-5", tone === "loading" && "animate-spin")}
            aria-hidden="true"
          />
        </div>
        <h2 className="mt-3 text-sm font-semibold text-[var(--v2-text-primary)]">
          {title}
        </h2>
        {description ? (
          <p
            className={cn(
              "mt-2 text-xs leading-6",
              tone === "error"
                ? "text-red-700"
                : "text-[var(--v2-text-secondary)]",
            )}
          >
            {description}
          </p>
        ) : null}
      </div>
    </div>
  );
}
