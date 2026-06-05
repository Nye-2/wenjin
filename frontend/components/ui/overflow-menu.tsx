"use client";

import { useEffect, useId, useRef, useState, type ComponentType } from "react";
import { MoreHorizontal } from "lucide-react";

import { IconButton } from "@/components/ui/icon-button";
import { cn } from "@/lib/utils";

export type OverflowMenuItem = {
  label: string;
  onClick: () => void;
  icon?: ComponentType<{ className?: string }>;
  tone?: "default" | "danger";
  disabled?: boolean;
};

export function OverflowMenu({ items }: { items: OverflowMenuItem[] }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) {
      return;
    }

    const closeOnOutsideMouseDown = (event: MouseEvent) => {
      const target = event.target;
      if (target instanceof Node && rootRef.current?.contains(target)) {
        return;
      }
      setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    document.addEventListener("mousedown", closeOnOutsideMouseDown);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideMouseDown);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  if (items.length === 0) {
    return null;
  }

  return (
    <div ref={rootRef} className="relative inline-flex">
      <IconButton
        label="更多操作"
        aria-controls={open ? menuId : undefined}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((current) => !current)}
      >
        <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
      </IconButton>
      {open ? (
        <div
          id={menuId}
          role="menu"
          className="absolute right-0 top-9 z-40 min-w-36 rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white p-1 shadow-[var(--wjn-shadow-md)]"
        >
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.label}
                type="button"
                role="menuitem"
                disabled={item.disabled}
                onClick={() => {
                  setOpen(false);
                  item.onClick();
                }}
                className={cn(
                  "flex h-8 w-full items-center gap-2 rounded-[var(--wjn-radius)] px-2 text-left text-xs font-medium transition-colors disabled:pointer-events-none disabled:opacity-45",
                  item.tone === "danger"
                    ? "text-[var(--wjn-error)] hover:bg-[var(--wjn-error-soft)]"
                    : "text-[var(--wjn-text-secondary)] hover:bg-[var(--wjn-surface-subtle)] hover:text-[var(--wjn-text)]",
                )}
              >
                {Icon ? <Icon className="h-3.5 w-3.5" aria-hidden="true" /> : null}
                <span className="truncate">{item.label}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
