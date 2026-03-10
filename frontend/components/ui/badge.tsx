import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/50",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-[var(--accent-primary)]/15 text-[var(--accent-secondary)]",
        secondary:
          "border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--text-secondary)]",
        destructive:
          "border-red-500/30 bg-red-500/10 text-red-400",
        success:
          "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
        warning:
          "border-amber-500/30 bg-amber-500/10 text-amber-400",
        outline:
          "border-[var(--border-default)] bg-transparent text-[var(--text-secondary)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
