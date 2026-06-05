"use client";

import { GripVertical } from "lucide-react";
import {
  Group,
  Panel,
  Separator,
  type GroupProps,
  type PanelProps,
  type SeparatorProps,
} from "react-resizable-panels";
import { cn } from "@/lib/utils";

const ResizablePanelGroup = ({
  className,
  ...props
}: GroupProps) => (
  <Group
    className={cn(
      "flex h-full w-full data-[panel-group-direction=vertical]:flex-col data-[panel-group-orientation=vertical]:flex-col",
      className
    )}
    {...props}
  />
);

const ResizablePanel = (props: PanelProps) => <Panel {...props} />;

const ResizableHandle = ({
  withHandle,
  className,
  ...props
}: SeparatorProps & {
  withHandle?: boolean;
}) => (
  <Separator
    className={cn(
      "relative flex w-px items-center justify-center bg-[var(--wjn-line)]",
      "after:absolute after:inset-y-0 after:left-1/2 after:w-1 after:-translate-x-1/2",
      "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--wjn-blue)] focus-visible:ring-offset-1",
      "data-[panel-group-direction=vertical]:h-px data-[panel-group-direction=vertical]:w-full data-[panel-group-orientation=vertical]:h-px data-[panel-group-orientation=vertical]:w-full",
      "data-[panel-group-direction=vertical]:after:left-0 data-[panel-group-direction=vertical]:after:h-1 data-[panel-group-direction=vertical]:after:w-full data-[panel-group-direction=vertical]:after:-translate-y-1/2 data-[panel-group-direction=vertical]:after:translate-x-0",
      "data-[panel-group-orientation=vertical]:after:left-0 data-[panel-group-orientation=vertical]:after:h-1 data-[panel-group-orientation=vertical]:after:w-full data-[panel-group-orientation=vertical]:after:-translate-y-1/2 data-[panel-group-orientation=vertical]:after:translate-x-0",
      "[&[data-panel-group-direction=vertical]>div]:rotate-90 [&[data-panel-group-orientation=vertical]>div]:rotate-90",
      "hover:bg-[var(--wjn-evidence)]/30 transition-colors duration-200",
      className
    )}
    {...props}
  >
    {withHandle && (
      <div className="z-10 flex h-8 w-3 items-center justify-center rounded-sm border border-[var(--wjn-line)] bg-[var(--wjn-surface)] shadow-sm">
        <GripVertical className="h-4 w-4 text-[var(--wjn-text-muted)]" />
      </div>
    )}
  </Separator>
);

export { ResizablePanelGroup, ResizablePanel, ResizableHandle };
