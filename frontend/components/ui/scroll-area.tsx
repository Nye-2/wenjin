"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface ScrollAreaProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  direction?: "vertical" | "horizontal" | "both";
  theme?: "light" | "compute";
}

export function ScrollArea({
  children,
  className,
  direction = "vertical",
  theme = "light",
  ...props
}: ScrollAreaProps) {
  return (
    <div
      className={cn(
        "overflow-auto",
        direction === "vertical" && "overflow-x-hidden overflow-y-auto",
        direction === "horizontal" && "overflow-x-auto overflow-y-hidden",
        direction === "both" && "overflow-auto",
        theme === "compute" && "compute-scroll",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

interface ScrollAreaOverlayProps extends ScrollAreaProps {
  topOverlay?: boolean;
  bottomOverlay?: boolean;
}

export function ScrollAreaOverlay({
  children,
  className,
  direction = "vertical",
  theme = "light",
  topOverlay = true,
  bottomOverlay = true,
  ...props
}: ScrollAreaOverlayProps) {
  return (
    <div className={cn("relative", className)} {...props}>
      {topOverlay && (
        <div
          className={cn(
            "pointer-events-none absolute left-0 right-0 top-0 z-10 h-4",
            theme === "compute"
              ? "bg-gradient-to-b from-compute-base to-transparent"
              : "bg-gradient-to-b from-[var(--bg-base)] to-transparent"
          )}
        />
      )}
      <ScrollArea direction={direction} theme={theme} className="h-full">
        {children}
      </ScrollArea>
      {bottomOverlay && (
        <div
          className={cn(
            "pointer-events-none absolute bottom-0 left-0 right-0 z-10 h-4",
            theme === "compute"
              ? "bg-gradient-to-t from-compute-base to-transparent"
              : "bg-gradient-to-t from-[var(--bg-base)] to-transparent"
          )}
        />
      )}
    </div>
  );
}
