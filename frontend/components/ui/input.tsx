import * as React from "react";
import { cn } from "@/lib/utils";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-11 w-full rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-4 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] shadow-sm",
          "hover:border-[var(--accent-secondary)]/40",
          "focus:outline-none focus:border-[var(--border-focus)] focus:ring-4 focus:ring-[var(--accent-primary)]/15",
          "disabled:cursor-not-allowed disabled:bg-[var(--bg-surface)] disabled:text-[var(--text-muted)] disabled:opacity-100",
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
