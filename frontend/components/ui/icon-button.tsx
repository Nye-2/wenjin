import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  children: ReactNode;
  tone?: "default" | "danger";
};

export function IconButton({
  label,
  children,
  className,
  tone = "default",
  title,
  ...props
}: IconButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      title={title ?? label}
      className={cn(
        "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--wjn-radius)] border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wjn-blue)] disabled:pointer-events-none disabled:opacity-45",
        tone === "danger"
          ? "border-[rgba(185,28,28,0.24)] bg-[var(--wjn-error-soft)] text-[var(--wjn-error)] hover:bg-[rgba(185,28,28,0.14)]"
          : "border-[var(--wjn-line)] bg-[var(--wjn-surface)] text-[var(--wjn-text-secondary)] hover:border-[var(--wjn-accent-line)] hover:text-[var(--wjn-text)]",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
