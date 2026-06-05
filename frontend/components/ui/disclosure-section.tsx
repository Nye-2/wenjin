"use client";

import { useId, useState } from "react";
import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";

export function DisclosureSection({
  label,
  children,
  defaultOpen = false,
}: {
  label: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();

  return (
    <div className="rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between gap-2 rounded-[var(--wjn-radius-lg)] px-3 py-2 text-left text-xs font-semibold text-[var(--wjn-text-secondary)] transition-colors hover:bg-[var(--wjn-surface-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wjn-blue)]"
      >
        {label}
        <ChevronDown
          className={[
            "h-3.5 w-3.5 shrink-0 text-[var(--wjn-text-muted)] transition-transform",
            open ? "rotate-180" : "",
          ].join(" ")}
          aria-hidden="true"
        />
      </button>
      <div
        id={panelId}
        hidden={!open}
        className="border-t border-[var(--wjn-line)] p-3"
      >
        {children}
      </div>
    </div>
  );
}
