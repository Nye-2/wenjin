"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface PanelActionBarProps {
  children: ReactNode;
  className?: string;
}

export function PanelActionBar({ children, className }: PanelActionBarProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-2xl border border-[var(--border-default)] bg-white/76 p-3",
        className
      )}
    >
      {children}
    </div>
  );
}
