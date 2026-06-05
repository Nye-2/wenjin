import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function SectionHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        {eyebrow ? (
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--wjn-text-muted)]">
            {eyebrow}
          </div>
        ) : null}
        <div className="truncate text-sm font-semibold text-[var(--wjn-text)]">
          {title}
        </div>
        {description ? (
          <div className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--wjn-text-secondary)]">
            {description}
          </div>
        ) : null}
      </div>
      {actions ? <div className="shrink-0">{actions}</div> : null}
    </div>
  );
}
