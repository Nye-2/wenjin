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
      style={{ background: "var(--wjn-bg-material)" }}
    >
      <div
        data-testid={testId}
        className={cn(
          "w-full max-w-md rounded-[var(--wjn-radius-lg)] border px-5 py-5 text-center shadow-[var(--wjn-shadow-md)]",
          tone === "error"
            ? "border-[rgba(185,28,28,0.24)] bg-[var(--wjn-surface)]"
            : "border-[var(--wjn-line)] bg-[var(--wjn-surface)]",
        )}
      >
        <div
          className={cn(
            "mx-auto flex h-10 w-10 items-center justify-center rounded-full",
            tone === "error"
              ? "bg-[var(--wjn-error-soft)] text-[var(--wjn-error)]"
              : tone === "loading"
                ? "bg-[var(--wjn-accent-soft)] text-[var(--wjn-blue)]"
                : "bg-[var(--wjn-evidence-soft)] text-[var(--wjn-evidence)]",
          )}
        >
          <Icon
            className={cn("h-5 w-5", tone === "loading" && "animate-spin")}
            aria-hidden="true"
          />
        </div>
        <h2 className="mt-3 text-sm font-semibold text-[var(--wjn-text)]">
          {title}
        </h2>
        {description ? (
          <p
            className={cn(
              "mt-2 text-xs leading-6",
              tone === "error"
                ? "text-[var(--wjn-error)]"
                : "text-[var(--wjn-text-secondary)]",
            )}
          >
            {description}
          </p>
        ) : null}
      </div>
    </div>
  );
}
