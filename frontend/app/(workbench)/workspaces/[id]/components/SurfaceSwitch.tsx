"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { useOptionalI18n } from "@/components/i18n-provider";

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

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-[var(--v2-border-soft)] bg-[rgba(255,255,255,0.72)] px-3 py-2 backdrop-blur-xl sm:px-4"
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
      >
        {prismLabel}
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
        "inline-flex h-8 shrink-0 items-center rounded-[var(--v2-radius-pill)] px-3 text-sm font-medium transition-colors",
        active
          ? "bg-[var(--v2-accent-purple-100)] text-[var(--v2-accent-purple-700)]"
          : "text-[var(--v2-text-secondary)] hover:bg-[rgba(20,20,30,0.06)] hover:text-[var(--v2-text-primary)]",
      ].join(" ")}
    >
      {children}
    </Link>
  );
}
