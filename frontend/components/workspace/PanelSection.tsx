"use client";

import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface PanelSectionProps {
  title: string;
  icon?: LucideIcon;
  description?: string;
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function PanelSection({
  title,
  icon: Icon,
  description,
  actions,
  className,
  children,
}: PanelSectionProps) {
  return (
    <section className={cn("rounded-2xl border border-[var(--border-default)] bg-white/76 p-4", className)}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            {Icon ? <Icon className="h-4 w-4 text-[var(--brand-navy)]" /> : null}
            <h4 className="text-sm font-medium text-[var(--text-primary)]">{title}</h4>
          </div>
          {description ? (
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
              {description}
            </p>
          ) : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}
