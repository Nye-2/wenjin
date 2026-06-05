import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Panel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <section
      className={cn(
        "rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white text-[var(--wjn-text)] shadow-[var(--wjn-shadow-sm)]",
        className,
      )}
      {...props}
    />
  );
}
