"use client";

import { cn } from "@/lib/utils";

export interface PanelTabOption {
  id: string;
  label: string;
  count?: number | null;
}

interface PanelTabBarProps {
  tabs: PanelTabOption[];
  activeTab: string;
  onSelect: (tabId: string) => void;
  className?: string;
}

export function PanelTabBar({
  tabs,
  activeTab,
  onSelect,
  className,
}: PanelTabBarProps) {
  if (tabs.length <= 1) {
    return null;
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-2xl border border-[var(--border-default)] bg-white/76 p-2",
        className
      )}
    >
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onSelect(tab.id)}
            className={cn(
              "inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-medium transition-colors",
              isActive
                ? "bg-[var(--accent-primary)]/12 text-[var(--accent-primary)]"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
            )}
          >
            <span>{tab.label}</span>
            {typeof tab.count === "number" ? (
              <span
                className={cn(
                  "rounded-full px-1.5 py-0.5 text-[10px]",
                  isActive
                    ? "bg-white/80 text-[var(--accent-primary)]"
                    : "bg-[var(--bg-surface)] text-[var(--text-muted)]"
                )}
              >
                {tab.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
