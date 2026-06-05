import * as React from "react";
import { cn } from "@/lib/utils";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-11 w-full rounded-xl border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-4 py-2.5 text-sm text-[var(--wjn-text)] placeholder:text-[var(--wjn-text-muted)] shadow-sm",
          "hover:border-[var(--wjn-blue)]/40",
          "focus:outline-none focus:border-[var(--wjn-blue)] focus:ring-4 focus:ring-[var(--wjn-navy)]/15",
          "disabled:cursor-not-allowed disabled:bg-[var(--wjn-surface-subtle)] disabled:text-[var(--wjn-text-muted)] disabled:opacity-100",
          "transition-all duration-200",
          "file:border-0 file:bg-transparent file:text-sm file:font-medium",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
