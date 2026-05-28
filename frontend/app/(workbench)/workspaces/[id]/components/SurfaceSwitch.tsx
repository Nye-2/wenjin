"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { useOptionalI18n } from "@/components/i18n-provider";
import { useExecutionStore } from "@/stores/execution-store";

type SurfaceSwitchProps = {
  workspaceId: string;
  active: "workbench" | "prism";
};

export function SurfaceSwitch({ workspaceId, active }: SurfaceSwitchProps) {
  const i18n = useOptionalI18n();
  const t = i18n?.t;
  const workbenchLabel = t?.("workspaceSurfaces.workbench") ?? "Workbench";
  const prismLabel = t?.("workspaceSurfaces.prism") ?? "Prism";
  const ariaLabel =
    t?.("workspaceSurfaces.ariaLabel") ?? "Workspace surfaces";
  const prismPendingCount = useExecutionStore((state) =>
    Array.from(state.executions.values()).reduce((count, record) => {
      if (record.workspace_id && record.workspace_id !== workspaceId) {
        return count;
      }
      return count + (record.review_items?.length ?? 0);
    }, 0),
  );

  return (
    <header className="wjn-topbar flex shrink-0 items-center justify-between gap-3 px-3 py-2 sm:px-4">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] border border-[var(--wjn-line)] bg-white text-[13px] font-semibold text-[var(--wjn-accent-strong)] shadow-[var(--wjn-shadow-sm)]">
          问
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-[var(--wjn-text)]">
            Wenjin
          </div>
          <div className="hidden truncate text-[11px] text-[var(--wjn-text-muted)] sm:block">
            Research Navigation System
          </div>
        </div>
      </div>
      <nav
        role="tablist"
        aria-label={ariaLabel}
        className="flex shrink-0 items-center gap-1 overflow-x-auto rounded-[10px] border border-[var(--wjn-line)] bg-white/75 p-1"
      >
        <SurfaceTab
          href={`/workspaces/${workspaceId}`}
          active={active === "workbench"}
        >
          {workbenchLabel}
        </SurfaceTab>
        <SurfaceTab
          href={`/workspaces/${workspaceId}/prism`}
          active={active === "prism"}
          badge={prismPendingCount}
        >
          {prismLabel}
        </SurfaceTab>
      </nav>
    </header>
  );
}

function SurfaceTab({
  href,
  active,
  children,
  badge,
}: {
  href: string;
  active: boolean;
  children: ReactNode;
  badge?: number;
}) {
  return (
    <Link
      role="tab"
      aria-selected={active}
      href={href}
      className={[
        "inline-flex h-7 shrink-0 items-center rounded-[7px] px-3 text-[12.5px] font-semibold transition-colors",
        active
          ? "bg-[var(--wjn-accent-soft)] text-[var(--wjn-accent-strong)]"
          : "text-[var(--wjn-text-secondary)] hover:bg-[rgba(15,23,42,0.05)] hover:text-[var(--wjn-text)]",
      ].join(" ")}
    >
      {children}
      {badge ? (
        <span
          style={{
            marginLeft: 6,
            minWidth: 16,
            height: 16,
            borderRadius: 8,
            padding: "0 5px",
            background: "var(--wjn-review)",
            color: "#fff",
            fontSize: 10,
            lineHeight: "16px",
            fontWeight: 700,
          }}
        >
          {Math.min(badge, 99)}
        </span>
      ) : null}
    </Link>
  );
}
