"use client";

import { FileCheck2 } from "lucide-react";
import type { ReactNode } from "react";

import type { WorkspacePrismReviewItem } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export function prismReviewItemPath(item: WorkspacePrismReviewItem): string {
  return (
    item.target?.file_path?.trim() ||
    item.target?.path?.trim() ||
    item.logical_key?.trim() ||
    item.title
  );
}

export function prismReviewItemHref(
  workspaceId: string,
  item?: WorkspacePrismReviewItem | null,
): string {
  const params = new URLSearchParams({ focus: "file_changes" });
  if (item?.id) {
    params.set("review_item_id", item.id);
  }
  if (item?.logical_key) {
    params.set("logical_key", item.logical_key);
  }
  return `/workspaces/${workspaceId}/prism?${params.toString()}`;
}

export function prismReviewItemSummary(item: WorkspacePrismReviewItem): string | null {
  const summary = item.summary?.trim();
  return summary || null;
}

function reviewItemSummaryForDisplay(item: WorkspacePrismReviewItem, path: string): string | null {
  const summary = prismReviewItemSummary(item);
  if (!summary || summary === path || summary === item.title) {
    return null;
  }
  return summary;
}

function statusLabel(status: string): string {
  if (status === "pending") return "待复核";
  if (status === "applied") return "已写入";
  if (status === "rejected") return "已忽略";
  if (status === "reverted") return "已撤回";
  return status;
}

function statusClass(status: string): string {
  if (status === "applied") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-700";
  }
  if (status === "rejected" || status === "reverted") {
    return "border-red-500/20 bg-red-500/10 text-red-700";
  }
  return "border-amber-500/25 bg-amber-500/10 text-amber-800";
}

export function fileChangeToPrismReviewItem(
  change: {
    id?: string | null;
    logical_key: string;
    path: string;
    reason?: string | null;
    status?: string | null;
    title?: string | null;
    source_type?: string | null;
    source_mission_id?: string | null;
    source_task_id?: string | null;
    target_kind?: string | null;
    applied_at?: string | null;
    pending_hash?: string | null;
    current_hash?: string | null;
  },
): WorkspacePrismReviewItem {
  return {
    id: change.id || change.logical_key,
    kind: change.target_kind || "prism_file_change",
    logical_key: change.logical_key,
    status: change.status || "pending",
    title: change.title || change.path,
    summary: change.reason || null,
    source: {
      type: change.source_type || null,
      mission_id: change.source_mission_id || null,
      task_id: change.source_task_id || null,
    },
    target: {
      kind: change.target_kind || "prism_file_change",
      file_path: change.path,
      room: null,
      item_id: null,
    },
    preview: {
      mode: "diff",
      pending_hash: change.pending_hash || null,
      current_hash: change.current_hash || null,
    },
    actions: [],
    applied_at: change.applied_at || null,
  };
}

interface PrismReviewListProps {
  items: WorkspacePrismReviewItem[];
  emptyMessage?: string;
  className?: string;
  focusedItemId?: string | null;
  focusedLogicalKey?: string | null;
  renderActions?: (item: WorkspacePrismReviewItem) => ReactNode;
  renderDetails?: (item: WorkspacePrismReviewItem) => ReactNode;
}

function isFocusedReviewItem(
  item: WorkspacePrismReviewItem,
  focusedItemId?: string | null,
  focusedLogicalKey?: string | null,
): boolean {
  return Boolean(
    (focusedItemId && item.id === focusedItemId) ||
      (focusedLogicalKey && item.logical_key === focusedLogicalKey),
  );
}

export function PrismReviewList({
  items,
  emptyMessage = "暂无待复核修改",
  className,
  focusedItemId,
  focusedLogicalKey,
  renderActions,
  renderDetails,
}: PrismReviewListProps) {
  if (items.length === 0) {
    return (
      <div
        className={cn(
          "rounded-lg border border-[var(--wjn-line)] bg-white/65 px-3 py-3 text-xs text-[var(--wjn-text-secondary)]",
          className,
        )}
      >
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className={cn("space-y-2", className)}>
      {items.map((item) => {
        const path = prismReviewItemPath(item);
        const summary = reviewItemSummaryForDisplay(item, path);
        const isFocused = isFocusedReviewItem(
          item,
          focusedItemId,
          focusedLogicalKey,
        );
        return (
          <div
            key={`${item.id}:${item.status}`}
            data-review-item-id={item.id}
            data-review-logical-key={item.logical_key}
            className={cn(
              "rounded-lg border border-[var(--wjn-line)] bg-white/75 px-3 py-3",
              isFocused &&
                "border-[var(--wjn-accent-line)] bg-white shadow-[0_0_0_3px_rgba(44,93,160,0.12)]",
            )}
          >
            <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 items-center gap-2">
                  <FileCheck2 className="h-3.5 w-3.5 shrink-0 text-[var(--wjn-text-secondary)]" />
                  <p className="truncate text-xs font-medium text-[var(--wjn-text)]">
                    {item.title || path}
                  </p>
                  <span
                    className={cn(
                      "shrink-0 rounded-full border px-2 py-0.5 text-[10px]",
                      statusClass(item.status),
                    )}
                  >
                    {statusLabel(item.status)}
                  </span>
                </div>
                {path && path !== item.title ? (
                  <p className="mt-1 truncate text-[11px] text-[var(--wjn-text-secondary)]">
                    {path}
                  </p>
                ) : null}
                {summary ? (
                  <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-[var(--wjn-text-secondary)]">
                    {summary}
                  </p>
                ) : null}
              </div>
              {renderActions ? (
                <div className="flex flex-wrap gap-2 sm:justify-end">
                  {renderActions(item)}
                </div>
              ) : null}
            </div>
            {renderDetails ? renderDetails(item) : null}
          </div>
        );
      })}
    </div>
  );
}
