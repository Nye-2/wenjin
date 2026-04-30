"use client";

import { cn } from "@/lib/utils";

export const SUPPORTED_BLOCK_ACTIONS = [
  "trigger_feature",
  "continue_thread",
  "open_feature",
  "rerun_from_artifact",
  "open_prism",
  "preview_prism_changes",
  "open_artifact",
  "rerun_feature",
  "resume_execution",
  "import_references",
] as const;

export type BlockActionType = (typeof SUPPORTED_BLOCK_ACTIONS)[number];

export function isBlockActionType(value: unknown): value is BlockActionType {
  return (
    typeof value === "string" &&
    (SUPPORTED_BLOCK_ACTIONS as readonly string[]).includes(value)
  );
}

export interface BlockActionItem {
  label: string;
  action: BlockActionType;
  featureId?: string | null;
  routeParams?: Record<string, unknown>;
  disabled?: boolean;
  title?: string;
}

export function BlockActionButtons({
  actions,
  onAction,
}: {
  actions: BlockActionItem[];
  onAction?: (
    action: BlockActionType,
    featureId: string | null,
    routeParams?: Record<string, unknown> | null
  ) => void;
}) {
  if (actions.length === 0 || !onAction) {
    return null;
  }

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {actions.map((item, index) => (
        <button
          key={`${item.action}-${item.featureId || "none"}-${index}`}
          type="button"
          disabled={Boolean(item.disabled)}
          title={item.title}
          onClick={() =>
            onAction?.(
              item.action,
              item.featureId ?? null,
              item.routeParams ?? null
            )
          }
          className={cn(
            "rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
            item.disabled
              ? "cursor-not-allowed border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--text-muted)] opacity-70"
              : "border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--text-primary)] hover:bg-[var(--bg-muted)]"
          )}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

export function readStringValue(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export function readNumberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function readArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}
