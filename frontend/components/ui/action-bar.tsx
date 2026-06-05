"use client";

import type { ComponentType } from "react";

import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { OverflowMenu, type OverflowMenuItem } from "@/components/ui/overflow-menu";
import { cn } from "@/lib/utils";

export type ActionBarAction = {
  label: string;
  onClick: () => void;
  icon?: ComponentType<{ className?: string }>;
  disabled?: boolean;
  iconOnly?: boolean;
  tone?: "default" | "danger";
};

export function ActionBar({
  primary,
  secondary = [],
  overflow = [],
  className,
}: {
  primary?: ActionBarAction;
  secondary?: ActionBarAction[];
  overflow?: OverflowMenuItem[];
  className?: string;
}) {
  const PrimaryIcon = primary?.icon;

  return (
    <div className={cn("flex min-w-0 items-center justify-end gap-2", className)}>
      {primary ? (
        <Button
          type="button"
          size="sm"
          disabled={primary.disabled}
          onClick={primary.onClick}
          className="gap-1.5"
        >
          {PrimaryIcon ? <PrimaryIcon className="h-3.5 w-3.5" aria-hidden="true" /> : null}
          {primary.label}
        </Button>
      ) : null}
      {secondary.map((action) => {
        const Icon = action.icon;
        if (action.iconOnly) {
          return (
            <IconButton
              key={action.label}
              label={action.label}
              disabled={action.disabled}
              tone={action.tone}
              onClick={action.onClick}
            >
              {Icon ? <Icon className="h-4 w-4" aria-hidden="true" /> : null}
            </IconButton>
          );
        }
        return (
          <Button
            key={action.label}
            type="button"
            variant={action.tone === "danger" ? "destructive" : "outline"}
            size="sm"
            disabled={action.disabled}
            onClick={action.onClick}
            className="gap-1.5"
          >
            {Icon ? <Icon className="h-3.5 w-3.5" aria-hidden="true" /> : null}
            {action.label}
          </Button>
        );
      })}
      {overflow.length > 0 ? <OverflowMenu items={overflow} /> : null}
    </div>
  );
}
