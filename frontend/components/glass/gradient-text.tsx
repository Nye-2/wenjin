"use client";

import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface GradientTextProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "subtle" | "shimmer";
}

export function GradientText({
  children,
  className,
  variant = "default",
  ...props
}: GradientTextProps) {
  if (variant === "default") {
    return (
      <span
        className={cn("text-[var(--text-primary)]", className)}
        {...props}
      >
        {children}
      </span>
    );
  }

  if (variant === "subtle") {
    return (
      <span
        className={cn(
          "bg-clip-text text-transparent",
          "bg-gradient-to-r from-[var(--accent-primary)] to-[var(--accent-secondary)]",
          className
        )}
        {...props}
      >
        {children}
      </span>
    );
  }

  // shimmer variant - uses global CSS class
  return (
    <span
      className={cn("gradient-text-shimmer", className)}
      {...props}
    >
      {children}
    </span>
  );
}
