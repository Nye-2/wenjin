import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface GradientTextProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "primary" | "secondary" | "shimmer";
}

export function GradientText({
  children,
  className,
  variant = "primary",
  ...props
}: GradientTextProps) {
  return (
    <span
      className={cn(
        "bg-clip-text text-transparent",
        variant === "primary" && "bg-gradient-to-r from-academic-primary via-purple-600 to-academic-secondary",
        variant === "secondary" && "bg-gradient-to-r from-academic-secondary to-emerald-500",
        variant === "shimmer" && "animate-gradient-x bg-[length:200%_auto] bg-gradient-to-r from-academic-primary via-purple-600 to-academic-primary",
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
}
