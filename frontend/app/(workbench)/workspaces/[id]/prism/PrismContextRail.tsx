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
    <span className="inline-flex items-center gap-1.5 rounded-md border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-2.5 py-1 text-xs text-[var(--wjn-text-secondary)]">
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
    recentActivity.length > 0;

  if (!hasContext) {
    return null;
  }

  return (
    <aside className="wjn-prism-context-rail px-4 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-md border border-[rgba(180,83,9,0.24)] bg-[var(--wjn-review-soft)] px-2.5 py-1 text-xs text-[var(--wjn-review)]">
            <FileCheck2 className="h-3.5 w-3.5" />
            <span className="font-medium">{pendingCount}</span>
            待复核
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-md border border-[rgba(15,118,110,0.22)] bg-[var(--wjn-evidence-soft)] px-2.5 py-1 text-xs text-[var(--wjn-evidence)]">
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
