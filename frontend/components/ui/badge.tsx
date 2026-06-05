import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--wjn-blue)]/40",
  {
    variants: {
      variant: {
        default:
          "border-[var(--wjn-accent-line)] bg-[var(--wjn-accent-soft)] text-[var(--wjn-blue-strong)]",
        secondary:
          "border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] text-[var(--wjn-text-secondary)]",
        destructive:
          "border-[rgba(185,28,28,0.28)] bg-[var(--wjn-error-soft)] text-[var(--wjn-error)]",
        success:
          "border-[rgba(15,118,110,0.28)] bg-[var(--wjn-evidence-soft)] text-[var(--wjn-evidence)]",
        warning:
          "border-[rgba(180,83,9,0.28)] bg-[var(--wjn-review-soft)] text-[var(--wjn-review)]",
        outline:
          "border-[var(--wjn-line)] bg-transparent text-[var(--wjn-text-secondary)]",
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
