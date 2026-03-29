"use client";

import { useRouter, usePathname } from "next/navigation";
import {
  MessageSquare,
  LayoutDashboard,
  Plus,
  ChevronLeft,
  ChevronRight,
  Trash2,
  Loader2,
} from "lucide-react";
import { useChatStore } from "@/stores/chat";
import { useWorkspaceStore } from "@/stores/workspace";
import { cn } from "@/lib/utils";
import type { ThreadSummary } from "@/lib/api";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface AppShellSidebarProps {
  workspaceId: string;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AppShellSidebar({
  workspaceId,
  collapsed = false,
  onToggleCollapse,
}: AppShellSidebarProps) {
  const router = useRouter();
  const pathname = usePathname();

  // Store selectors
  const threads = useChatStore((s) => s.threads);
  const activeThreadId = useChatStore((s) => s.threadId);
  const isThreadsLoading = useChatStore((s) => s.isThreadsLoading);
  const startNewThread = useChatStore((s) => s.startNewThread);
  const deleteThread = useChatStore((s) => s.deleteThread);
  const workspaces = useWorkspaceStore((s) => s.workspaces);

  // Route detection
  const isOnChat = pathname.includes("/chat/");
  const isOnDashboard = !isOnChat;

  // Workspace name lookup
  const workspaceName =
    workspaces.find((ws) => ws.id === workspaceId)?.name ?? "Workspace";

  // Navigation helpers
  const goToDashboard = () => router.push(`/workspaces/${workspaceId}`);
  const goToNewChat = () => {
    startNewThread();
    router.push(`/workspaces/${workspaceId}/chat/new`);
  };
  const goToThread = (threadId: string) =>
    router.push(`/workspaces/${workspaceId}/chat/${threadId}`);
  const handleDeleteThread = (e: React.MouseEvent, threadId: string) => {
    e.stopPropagation();
    void deleteThread(threadId, workspaceId);
  };

  // -------------------------------------------------------------------------
  // Collapsed mode
  // -------------------------------------------------------------------------

  if (collapsed) {
    return (
      <aside
        className={cn(
          "flex w-12 shrink-0 flex-col items-center gap-2 border-r border-[var(--border-default)] bg-[var(--bg-surface)] py-3"
        )}
      >
        {/* Expand toggle */}
        <button
          onClick={onToggleCollapse}
          className="rounded-md p-2 text-[var(--text-secondary)] hover:bg-[var(--bg-muted)] transition-colors"
          title="Expand sidebar"
        >
          <ChevronRight className="h-4 w-4" />
        </button>

        {/* Dashboard */}
        <button
          onClick={goToDashboard}
          className={cn(
            "rounded-md p-2 transition-colors",
            isOnDashboard
              ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
              : "text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]"
          )}
          title="Dashboard"
        >
          <LayoutDashboard className="h-4 w-4" />
        </button>

        {/* New chat */}
        <button
          onClick={goToNewChat}
          className="rounded-md border border-dashed border-[var(--border-default)] p-2 text-[var(--text-secondary)] hover:bg-[var(--bg-muted)] transition-colors"
          title="New chat"
        >
          <Plus className="h-4 w-4" />
        </button>
      </aside>
    );
  }

  // -------------------------------------------------------------------------
  // Expanded mode
  // -------------------------------------------------------------------------

  return (
    <aside
      className={cn(
        "flex w-60 shrink-0 flex-col border-r border-[var(--border-default)] bg-[var(--bg-surface)]"
      )}
    >
      {/* Header: workspace name + collapse toggle */}
      <div className="flex items-center justify-between border-b border-[var(--border-default)] px-3 py-3">
        <span className="truncate text-sm font-semibold text-[var(--text-primary)]">
          {workspaceName}
        </span>
        <button
          onClick={onToggleCollapse}
          className="rounded-md p-1 text-[var(--text-secondary)] hover:bg-[var(--bg-muted)] transition-colors"
          title="Collapse sidebar"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
      </div>

      {/* View Switcher: Dashboard */}
      <div className="px-2 pt-2">
        <button
          onClick={goToDashboard}
          className={cn(
            "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
            isOnDashboard
              ? "bg-[var(--accent-primary)]/10 font-medium text-[var(--accent-primary)]"
              : "text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]"
          )}
        >
          <LayoutDashboard className="h-4 w-4 shrink-0" />
          Dashboard
        </button>
      </div>

      {/* New Chat button */}
      <div className="px-2 pt-2">
        <button
          onClick={goToNewChat}
          className={cn(
            "flex w-full items-center gap-2 rounded-md border border-dashed border-[var(--border-default)] px-2 py-1.5 text-sm",
            "text-[var(--text-secondary)] hover:bg-[var(--bg-muted)] transition-colors"
          )}
        >
          <Plus className="h-4 w-4 shrink-0" />
          New Chat
        </button>
      </div>

      {/* Thread list */}
      <div className="mt-2 flex-1 overflow-y-auto px-2 pb-2">
        {isThreadsLoading ? (
          <div className="flex items-center justify-center py-6 text-[var(--text-muted)]">
            <Loader2 className="h-4 w-4 animate-spin" />
          </div>
        ) : threads.length === 0 ? (
          <p className="px-2 py-4 text-center text-xs text-[var(--text-muted)]">
            No conversations yet
          </p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {threads.map((thread: ThreadSummary) => {
              const isActive = isOnChat && thread.id === activeThreadId;
              return (
                <li key={thread.id}>
                  <button
                    onClick={() => goToThread(thread.id)}
                    className={cn(
                      "group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                      isActive
                        ? "bg-[var(--bg-elevated)] font-medium text-[var(--text-primary)]"
                        : "text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]"
                    )}
                  >
                    <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                    <span className="min-w-0 flex-1 truncate">
                      {thread.title ?? "Untitled"}
                    </span>
                    <span
                      role="button"
                      tabIndex={0}
                      onClick={(e) => handleDeleteThread(e, thread.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          handleDeleteThread(
                            e as unknown as React.MouseEvent,
                            thread.id
                          );
                        }
                      }}
                      className="ml-auto hidden shrink-0 rounded p-0.5 text-[var(--text-muted)] hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] group-hover:inline-flex transition-colors"
                      title="Delete thread"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Bottom: All Workspaces link */}
      <div className="border-t border-[var(--border-default)] px-2 py-2">
        <button
          onClick={() => router.push("/workspaces")}
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-[var(--text-muted)] hover:bg-[var(--bg-muted)] hover:text-[var(--text-secondary)] transition-colors"
        >
          <ChevronLeft className="h-4 w-4 shrink-0" />
          All Workspaces
        </button>
      </div>
    </aside>
  );
}
