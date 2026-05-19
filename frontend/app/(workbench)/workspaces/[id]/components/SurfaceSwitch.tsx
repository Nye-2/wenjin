"use client";

import Link from "next/link";
import type { ReactNode } from "react";

type SurfaceSwitchProps = {
  workspaceId: string;
  active: "workbench" | "prism";
};

export function SurfaceSwitch({ workspaceId, active }: SurfaceSwitchProps) {
  return (
    <div
      role="tablist"
      aria-label="Workspace surfaces"
      className="flex items-center gap-1 border-b border-[var(--v2-border-soft)] bg-[rgba(255,255,255,0.72)] px-4 py-2 backdrop-blur-xl"
    >
      <SurfaceTab
        href={`/workspaces/${workspaceId}`}
        active={active === "workbench"}
      >
        Workbench
      </SurfaceTab>
      <SurfaceTab
        href={`/workspaces/${workspaceId}/prism`}
        active={active === "prism"}
      >
        Prism
      </SurfaceTab>
    </div>
  );
}

function SurfaceTab({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <Link
      role="tab"
      aria-selected={active}
      href={href}
      className={[
        "inline-flex h-8 items-center rounded-[var(--v2-radius-pill)] px-3 text-sm font-medium transition-colors",
        active
          ? "bg-[var(--v2-accent-purple-100)] text-[var(--v2-accent-purple-700)]"
          : "text-[var(--v2-text-secondary)] hover:bg-[rgba(20,20,30,0.06)] hover:text-[var(--v2-text-primary)]",
      ].join(" ")}
    >
      {children}
    </Link>
  );
}
