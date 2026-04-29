"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Menu, X } from "lucide-react";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { KnowledgeRail } from "@/components/knowledge/KnowledgeRail";
import { cn } from "@/lib/utils";

export type WorkspaceMode = "chat" | "executing" | "completed";

interface WorkspaceShellProps {
  workspaceId: string;
  chatPanel: React.ReactNode;
  computePanel: React.ReactNode;
  className?: string;
}

const PANEL_IDS = {
  knowledge: "knowledge",
  compute: "compute",
  chat: "chat",
};

function getDefaultLayout(mode: WorkspaceMode): Record<string, number> {
  switch (mode) {
    case "chat":
      return { [PANEL_IDS.knowledge]: 15, [PANEL_IDS.compute]: 0, [PANEL_IDS.chat]: 85 };
    case "executing":
      return { [PANEL_IDS.knowledge]: 12, [PANEL_IDS.compute]: 58, [PANEL_IDS.chat]: 30 };
    case "completed":
      return { [PANEL_IDS.knowledge]: 12, [PANEL_IDS.compute]: 48, [PANEL_IDS.chat]: 40 };
    default:
      return { [PANEL_IDS.knowledge]: 15, [PANEL_IDS.compute]: 0, [PANEL_IDS.chat]: 85 };
  }
}

const STORAGE_KEY = "wenjin:workspace-shell-layout";

function loadSavedLayout(workspaceId: string): Record<string, number> | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed[workspaceId] ?? null;
  } catch {
    return null;
  }
}

function saveLayout(workspaceId: string, layout: Record<string, number>) {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const all = raw ? JSON.parse(raw) : {};
    all[workspaceId] = layout;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch {
    // ignore
  }
}

export function WorkspaceShell({
  workspaceId,
  chatPanel,
  computePanel,
  className,
}: WorkspaceShellProps) {
  const [mode, setMode] = useState<WorkspaceMode>("chat"); // eslint-disable-line @typescript-eslint/no-unused-vars
  const [mobileRailOpen, setMobileRailOpen] = useState(false);

  const defaultLayout =
    loadSavedLayout(workspaceId) ?? getDefaultLayout(mode);

  const isComputeVisible = mode === "executing" || mode === "completed";

  return (
    <div className={cn("relative flex h-full w-full", className)}>
      {/* Mobile Knowledge Rail Drawer */}
      <AnimatePresence>
        {mobileRailOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 z-40 bg-black/40 lg:hidden"
              onClick={() => setMobileRailOpen(false)}
            />
            <motion.div
              initial={{ x: -240 }}
              animate={{ x: 0 }}
              exit={{ x: -240 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] as const }}
              className="absolute left-0 top-0 z-50 h-full w-60 lg:hidden"
            >
              <KnowledgeRail workspaceId={workspaceId} className="h-full" />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Mobile Toggle Button */}
      <button
        onClick={() => setMobileRailOpen((prev) => !prev)}
        className={cn(
          "absolute left-3 top-3 z-30 flex h-8 w-8 items-center justify-center rounded-lg border lg:hidden",
          mobileRailOpen
            ? "border-compute-border bg-compute-elevated text-compute-text-primary"
            : "border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]"
        )}
      >
        {mobileRailOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
      </button>

      <ResizablePanelGroup
        orientation="horizontal"
        defaultLayout={defaultLayout}
        onLayoutChanged={(layout) => saveLayout(workspaceId, layout)}
      >
        {/* Knowledge Rail - hidden on mobile, shown on lg+ */}
        <ResizablePanel
          id={PANEL_IDS.knowledge}
          defaultSize={defaultLayout[PANEL_IDS.knowledge]}
          minSize={8}
          maxSize={25}
          collapsible
          collapsedSize={4}
          className="hidden lg:block"
        >
          <KnowledgeRail workspaceId={workspaceId} className="h-full" />
        </ResizablePanel>

        <ResizableHandle withHandle className="hidden lg:flex" />

        {/* Compute Stage */}
        <ResizablePanel
          id={PANEL_IDS.compute}
          defaultSize={defaultLayout[PANEL_IDS.compute]}
          minSize={0}
          maxSize={80}
          collapsible
          collapsedSize={0}
        >
          <AnimatePresence mode="wait">
            {isComputeVisible ? (
              <motion.div
                key="compute"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{
                  duration: 0.4,
                  ease: [0.16, 1, 0.3, 1] as const,
                }}
                className="h-full"
              >
                {computePanel}
              </motion.div>
            ) : (
              <motion.div
                key="compute-empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex h-full items-center justify-center bg-[var(--bg-base)]"
              >
                <ComputeEmptyState />
              </motion.div>
            )}
          </AnimatePresence>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Chat Dock */}
        <ResizablePanel
          id={PANEL_IDS.chat}
          defaultSize={defaultLayout[PANEL_IDS.chat]}
          minSize={20}
          maxSize={60}
        >
          <motion.div
            initial={false}
            animate={{ opacity: 1 }}
            transition={{
              duration: 0.3,
              ease: [0.16, 1, 0.3, 1] as const,
            }}
            className="h-full"
          >
            {chatPanel}
          </motion.div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}

function ComputeEmptyState() {
  return (
    <div className="flex flex-col items-center gap-3 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-compute-elevated">
        <svg
          className="h-8 w-8 text-compute-text-muted"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M3 9h18M9 21V9" />
        </svg>
      </div>
      <div>
        <p className="text-sm font-medium text-compute-text-secondary">
          计算工作台
        </p>
        <p className="mt-1 text-xs text-compute-text-muted">
          启动一个功能后，任务执行过程将在此展示
        </p>
      </div>
    </div>
  );
}

// Mode control hook for external components
export function useWorkspaceMode() {
  const [mode, setMode] = useState<WorkspaceMode>("chat");

  const enterExecution = useCallback(() => setMode("executing"), []);
  const completeExecution = useCallback(() => setMode("completed"), []);
  const returnToChat = useCallback(() => setMode("chat"), []);

  return {
    mode,
    setMode,
    enterExecution,
    completeExecution,
    returnToChat,
  };
}
