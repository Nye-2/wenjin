"use client";

import { cn } from "@/lib/utils";

export type StatusVariant =
  | "running"
  | "success"
  | "failed"
  | "warning"
  | "pending"
  | "idle"
  | "awaiting";

interface StatusIndicatorProps {
  variant: StatusVariant;
  size?: "sm" | "md" | "lg";
  className?: string;
  pulse?: boolean;
}

const variantStyles: Record<StatusVariant, string> = {
  running: "bg-compute-cyan",
  success: "bg-compute-green",
  failed: "bg-compute-red",
  warning: "bg-compute-gold",
  pending: "bg-compute-text-muted",
  idle: "bg-compute-border",
  awaiting: "bg-compute-gold",
};

const sizeStyles = {
  sm: "w-1.5 h-1.5",
  md: "w-2 h-2",
  lg: "w-2.5 h-2.5",
};

export function StatusIndicator({
  variant,
  size = "md",
  className,
  pulse = true,
}: StatusIndicatorProps) {
  return (
    <span
      className={cn(
        "inline-block rounded-full",
        variantStyles[variant],
        sizeStyles[size],
        pulse && variant === "running" && "status-running",
        className
      )}
    />
  );
}

interface StatusBadgeProps {
  variant: StatusVariant;
  label: string;
  className?: string;
}

const badgeBgStyles: Record<StatusVariant, string> = {
  running: "bg-compute-cyan/10 text-compute-cyan border-compute-cyan/20",
  success: "bg-compute-green/10 text-compute-green border-compute-green/20",
  failed: "bg-compute-red/10 text-compute-red border-compute-red/20",
  warning: "bg-compute-gold/10 text-compute-gold border-compute-gold/20",
  pending: "bg-compute-text-muted/10 text-compute-text-muted border-compute-text-muted/20",
  idle: "bg-compute-border/30 text-compute-text-muted border-compute-border/40",
  awaiting: "bg-compute-gold/10 text-compute-gold border-compute-gold/20",
};

export function StatusBadge({ variant, label, className }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        badgeBgStyles[variant],
        className
      )}
    >
      <StatusIndicator variant={variant} size="sm" pulse={variant === "running"} />
      {label}
    </span>
  );
}
