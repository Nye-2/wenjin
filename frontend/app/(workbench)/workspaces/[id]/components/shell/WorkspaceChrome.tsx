"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { Archive, BookOpenText, Eye, PanelsTopLeft } from "lucide-react";

import { CountBadge } from "@/components/ui/count-badge";
import { StatusChip } from "@/components/ui/status-chip";
import { useWenjinThemeStore } from "@/stores/wenjin-theme-store";

export type WorkspaceSurface = "workbench" | "prism";
export type WorkspaceMissionStatus = "running" | "waiting" | null;

export function WorkspaceChrome({
  workspaceId,
  workspaceName,
  workspaceTypeLabel,
  activeSurface,
  pendingReviewCount,
  missionStatus,
  missionSummaryState,
  onOpenHub,
}: {
  workspaceId: string;
  workspaceName?: string | null;
  workspaceTypeLabel?: string | null;
  activeSurface: WorkspaceSurface;
  pendingReviewCount: number;
  missionStatus: WorkspaceMissionStatus;
  missionSummaryState: "loading" | "ready" | "stale" | "unavailable";
  onOpenHub: () => void;
}) {
  const theme = useWenjinThemeStore((state) => state.theme);
  const toggleTheme = useWenjinThemeStore((state) => state.toggleTheme);
  const isGraphite = theme === "graphite";

  return (
    <header className="wjn-topbar flex shrink-0 items-center gap-2 px-3 py-2 sm:gap-3 sm:px-4">
      <Link
        href="/workspaces"
        aria-label="Wenjin"
        className="flex min-w-0 shrink-0 items-center gap-3 rounded-[var(--wjn-radius)] text-[var(--wjn-text)] no-underline outline-none transition-colors hover:text-[var(--wjn-accent-strong)] focus-visible:ring-2 focus-visible:ring-[var(--wjn-accent-line)]"
      >
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] border border-[var(--wjn-accent-line)] bg-[var(--wjn-navy)] text-[13px] font-semibold text-white shadow-[var(--wjn-shadow-sm)]">
          问
        </div>
        <div className="hidden min-w-0 sm:block">
          <div className="truncate text-sm font-semibold tracking-[-0.01em] text-[var(--wjn-text)]">
            Wenjin
          </div>
          <div className="truncate text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--wjn-text-muted)]">
            科研工作区
          </div>
        </div>
      </Link>

      <div className="hidden min-w-0 flex-1 items-center gap-3 md:flex">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-[var(--wjn-text)]">
            {workspaceName ?? "Workspace"}
          </div>
          <div className="truncate text-[11px] text-[var(--wjn-text-muted)]">
            {workspaceTypeLabel ?? "工作空间"}
          </div>
        </div>
        {missionStatus === "running" ? <StatusChip label="运行中" tone="running" /> : null}
        {missionStatus === "waiting" ? <StatusChip label="等待回应" tone="review" /> : null}
        {pendingReviewCount > 0 ? <StatusChip label="待确认" tone="review" /> : null}
        {missionSummaryState === "stale" || missionSummaryState === "unavailable" ? (
          <StatusChip label="状态待同步" tone="neutral" />
        ) : null}
      </div>

      <div className="ml-auto flex min-w-0 shrink-0 items-center justify-end gap-2">
        <nav
          role="tablist"
          aria-label="工作空间表面"
          className="flex shrink-0 items-center gap-1 rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] p-1 shadow-[var(--wjn-shadow-sm)]"
        >
          <SurfaceTab
            href={`/workspaces/${workspaceId}`}
            active={activeSurface === "workbench"}
            label="工作台"
            icon={<PanelsTopLeft className="h-3.5 w-3.5" aria-hidden="true" />}
          />
          <SurfaceTab
            href={`/workspaces/${workspaceId}/prism`}
            active={activeSurface === "prism"}
            label="写作台"
            count={pendingReviewCount}
            icon={<BookOpenText className="h-3.5 w-3.5" aria-hidden="true" />}
          />
        </nav>
        <button
          type="button"
          aria-label={isGraphite ? "切换到标准模式" : "切换到护眼模式"}
          title={isGraphite ? "切换到标准模式" : "切换到护眼模式"}
          aria-pressed={isGraphite}
          onClick={toggleTheme}
          className="inline-flex h-9 shrink-0 items-center gap-2 rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-3 text-xs font-semibold text-[var(--wjn-text-secondary)] shadow-[var(--wjn-shadow-sm)] transition-colors hover:border-[var(--wjn-accent-line)] hover:bg-[var(--wjn-surface-subtle)] hover:text-[var(--wjn-text)]"
        >
          <Eye className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">{isGraphite ? "标准" : "护眼"}</span>
        </button>
        <button
          type="button"
          aria-label={
            pendingReviewCount > 0
              ? `资料库，${pendingReviewCount} 项待确认`
              : "资料库"
          }
          title={
            pendingReviewCount > 0
              ? `资料库，${pendingReviewCount} 项待确认`
              : "资料库"
          }
          onClick={onOpenHub}
          className="relative inline-flex h-9 shrink-0 items-center gap-2 rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-3 text-xs font-semibold text-[var(--wjn-text-secondary)] shadow-[var(--wjn-shadow-sm)] transition-colors hover:border-[var(--wjn-accent-line)] hover:bg-[var(--wjn-surface-subtle)] hover:text-[var(--wjn-text)]"
        >
          <Archive className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">资料库</span>
          <CountBadge count={pendingReviewCount} tone="review" />
        </button>
      </div>
    </header>
  );
}

function SurfaceTab({
  href,
  active,
  label,
  icon,
  count = 0,
}: {
  href: string;
  active: boolean;
  label: string;
  icon: ReactNode;
  count?: number;
}) {
  return (
    <Link
      role="tab"
      aria-selected={active}
      aria-label={count > 0 ? `${label}，${count} 项待确认` : label}
      href={href}
      className={[
        "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-[var(--wjn-radius)] px-3 text-[12.5px] font-semibold transition-colors",
        active
          ? "bg-[var(--wjn-accent-soft)] text-[var(--wjn-accent-strong)]"
          : "text-[var(--wjn-text-secondary)] hover:bg-[var(--wjn-surface-subtle)] hover:text-[var(--wjn-text)]",
      ].join(" ")}
    >
      {icon}
      {label}
      <CountBadge count={count} tone="review" />
    </Link>
  );
}
