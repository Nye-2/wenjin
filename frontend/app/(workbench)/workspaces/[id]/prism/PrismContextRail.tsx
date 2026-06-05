"use client";

import {
  ArrowUpRight,
  CircleCheckBig,
  FileCheck2,
  History,
  Link2,
  ShieldCheck,
} from "lucide-react";

import type {
  WorkspacePrismSourceLink,
  WorkspacePrismSurfaceResponse,
} from "@/lib/api/types";

function count(value: number | null | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function displayText(value: string | null | undefined, fallback: string): string {
  const text = value?.trim();
  return text ? text : fallback;
}

function sourceLinkRoom(sourceType: string | null | undefined): string | null {
  const normalized = sourceType?.trim();
  if (normalized === "library" || normalized === "library_item") return "library";
  if (normalized === "document" || normalized === "documents") return "documents";
  return null;
}

function sourceLinkHref(
  workspaceId: string,
  link: WorkspacePrismSourceLink,
): string | null {
  const room = sourceLinkRoom(link.source_type);
  if (!room || !link.source_id) return null;
  const params = new URLSearchParams({
    room,
    item_id: link.source_id,
  });
  return `/workspaces/${workspaceId}?${params.toString()}`;
}

function ContextChip({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
}) {
  if (value <= 0) return null;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-white/55 bg-white/70 px-2.5 py-1 text-xs text-[var(--wjn-text-secondary)]">
      {icon}
      <span className="text-[var(--wjn-text)]">{value}</span>
      {label}
    </span>
  );
}

export function PrismContextRail({
  surface,
}: {
  surface: WorkspacePrismSurfaceResponse;
}) {
  const sourceLinks = surface.source_links ?? [];
  const protectedSections = surface.protected_sections ?? [];
  const decisions = surface.decisions ?? [];
  const memoryPreferences = surface.memory_preferences ?? [];
  const recentActivity = surface.recent_activity ?? [];
  const summary = surface.review_summary ?? {};
  const pendingCount = count(summary.pending_count);
  const appliedCount = count(summary.applied_count);
  const primarySource = sourceLinks[0] ?? null;
  const primarySourceHref = primarySource
    ? sourceLinkHref(surface.workspace_id, primarySource)
    : null;

  const hasContext =
    pendingCount > 0 ||
    appliedCount > 0 ||
    sourceLinks.length > 0 ||
    protectedSections.length > 0 ||
    decisions.length > 0 ||
    memoryPreferences.length > 0 ||
    recentActivity.length > 0;

  if (!hasContext) {
    return null;
  }

  return (
    <aside className="border-b border-white/45 bg-white/55 px-4 py-2 backdrop-blur-xl">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-md border border-amber-500/25 bg-amber-500/10 px-2.5 py-1 text-xs text-amber-900">
            <FileCheck2 className="h-3.5 w-3.5" />
            <span className="font-medium">{pendingCount}</span>
            待确认
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-md border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-900">
            <CircleCheckBig className="h-3.5 w-3.5" />
            <span className="font-medium">{appliedCount}</span>
            已写入
          </span>
          <ContextChip
            icon={<Link2 className="h-3.5 w-3.5" />}
            label="来源"
            value={sourceLinks.length}
          />
          <ContextChip
            icon={<History className="h-3.5 w-3.5" />}
            label="活动"
            value={recentActivity.length}
          />
          <ContextChip
            icon={<ShieldCheck className="h-3.5 w-3.5" />}
            label="保护段落"
            value={protectedSections.length}
          />
        </div>

        {primarySource ? (
          primarySourceHref ? (
            <a
              href={primarySourceHref}
              className="inline-flex max-w-full items-center gap-1.5 truncate rounded-md px-2 py-1 text-xs text-[var(--wjn-blue)] hover:bg-white/70"
            >
              <span className="truncate">
                {displayText(primarySource.citation_key, primarySource.source_id)}
              </span>
              <ArrowUpRight className="h-3.5 w-3.5 shrink-0" />
            </a>
          ) : (
            <span className="max-w-full truncate rounded-md px-2 py-1 text-xs text-[var(--wjn-text-secondary)]">
              {displayText(primarySource.citation_key, primarySource.source_id)}
            </span>
          )
        ) : null}
      </div>
    </aside>
  );
}
