"use client";

import Link from "next/link";
import { Archive } from "lucide-react";

import { CountBadge } from "@/components/ui/count-badge";
import { StatusChip } from "@/components/ui/status-chip";
import { syncCurrentAuthCookie } from "@/stores/auth";

export type WorkspaceSurface = "workbench" | "prism";

export function WorkspaceChrome({
  workspaceId,
  workspaceName,
  workspaceTypeLabel,
  activeSurface,
  pendingReviewCount,
  activeRunCount,
  onOpenHub,
}: {
  workspaceId: string;
  workspaceName?: string | null;
  workspaceTypeLabel?: string | null;
  activeSurface: WorkspaceSurface;
  pendingReviewCount: number;
  activeRunCount: number;
  onOpenHub: () => void;
}) {
  return (
    <header className="wjn-topbar flex shrink-0 items-center gap-2 px-3 py-2 sm:gap-3 sm:px-4">
      <Link
        href="/workspaces"
        aria-label="Wenjin"
        onClick={syncCurrentAuthCookie}
        className="flex min-w-0 shrink-0 items-center gap-3 rounded-[var(--wjn-radius)] text-[var(--wjn-text)] no-underline outline-none transition-colors hover:text-[var(--wjn-blue)] focus-visible:ring-2 focus-visible:ring-[var(--wjn-accent-line)]"
      >
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] border border-[rgba(255,255,255,0.56)] bg-[linear-gradient(145deg,var(--wjn-navy),var(--wjn-blue)_72%,#4d78b9)] text-[13px] font-semibold text-white shadow-[0_10px_24px_rgba(44,93,160,0.20)]">
          问
        </div>
        <div className="hidden min-w-0 sm:block">
          <div className="truncate text-sm font-semibold tracking-[-0.01em] text-[var(--wjn-text)]">
            Wenjin
          </div>
          <div className="truncate text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--wjn-text-muted)]">
            Research OS
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
        {activeRunCount > 0 ? <StatusChip label="运行中" tone="running" /> : null}
        {pendingReviewCount > 0 ? <StatusChip label="待审阅" tone="review" /> : null}
      </div>

      <div className="ml-auto flex min-w-0 shrink-0 items-center justify-end gap-2">
        <nav
          role="tablist"
          aria-label="工作空间表面"
          className="flex shrink-0 items-center gap-1 rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white p-1 shadow-[var(--wjn-shadow-sm)]"
        >
          <SurfaceTab
            href={`/workspaces/${workspaceId}`}
            active={activeSurface === "workbench"}
            label="Workbench"
          />
          <SurfaceTab
            href={`/workspaces/${workspaceId}/prism`}
            active={activeSurface === "prism"}
            label="Prism"
            count={pendingReviewCount}
          />
        </nav>
        <button
          type="button"
          aria-label={
            pendingReviewCount > 0
              ? `资料库，${pendingReviewCount} 项待审阅`
              : "资料库"
          }
          title={
            pendingReviewCount > 0
              ? `资料库，${pendingReviewCount} 项待审阅`
              : "资料库"
          }
          onClick={onOpenHub}
          className="relative inline-flex h-9 items-center gap-2 rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white px-3 text-xs font-semibold text-[var(--wjn-text-secondary)] shadow-[var(--wjn-shadow-sm)] transition-colors hover:border-[var(--wjn-accent-line)] hover:text-[var(--wjn-text)]"
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
  count = 0,
}: {
  href: string;
  active: boolean;
  label: string;
  count?: number;
}) {
  return (
    <Link
      role="tab"
      aria-selected={active}
      aria-label={count > 0 ? `${label}，${count} 项待审阅` : label}
      href={href}
      onClick={syncCurrentAuthCookie}
      className={[
        "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-[var(--wjn-radius)] px-3 text-[12.5px] font-semibold transition-colors",
        active
          ? "bg-[var(--wjn-accent-soft)] text-[var(--wjn-accent-strong)]"
          : "text-[var(--wjn-text-secondary)] hover:bg-[rgba(15,23,42,0.05)] hover:text-[var(--wjn-text)]",
      ].join(" ")}
    >
      {label}
      <CountBadge count={count} tone="review" />
    </Link>
  );
}
