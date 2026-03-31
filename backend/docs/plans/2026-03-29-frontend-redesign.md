# Frontend Redesign — Chat-Centric Architecture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure the frontend from 21+ independent feature pages to a 3-route chat-centric architecture with Dashboard + full-screen Chat views, where workspace features are triggered through chat skill selection.

**Architecture:** New AppShell layout with collapsible sidebar (workspace list, thread list, view switcher) wraps two main views: a simplified Dashboard (feature cards without status, active tasks, recent threads) and a full-screen ChatView (evolved from existing ChatPanel, with inline TaskCards and expandable TaskDetailPanel). Old feature routes redirect to `/workspaces/[id]/chat/new?skill=<skill-id>`.

**Tech Stack:** Next.js 16 (App Router), React 19, Zustand 5, TailwindCSS, Framer Motion, Lucide Icons

---

### Task 1: Create AppShell Sidebar Component

Build the new sidebar component that provides workspace and thread navigation across both Dashboard and Chat views.

**Files:**
- Create: `frontend/components/workspace/AppShellSidebar.tsx`
- Test: Manual visual inspection (React component — no unit tests for layout)

**Step 1: Create the AppShellSidebar component**

```tsx
// frontend/components/workspace/AppShellSidebar.tsx
"use client";

import { useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  MessageSquare,
  LayoutDashboard,
  Plus,
  ChevronLeft,
  ChevronRight,
  Trash2,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace";
import { useChatStore } from "@/stores/chat";
import type { ThreadSummary } from "@/lib/api";

interface AppShellSidebarProps {
  workspaceId: string;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function AppShellSidebar({
  workspaceId,
  collapsed = false,
  onToggleCollapse,
}: AppShellSidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { workspaces } = useWorkspaceStore();
  const {
    threads,
    threadId: activeThreadId,
    isThreadsLoading,
    startNewThread,
    deleteThread,
  } = useChatStore();
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const isChatView = pathname.includes("/chat/");
  const isDashboard = !isChatView;

  const handleNewChat = () => {
    startNewThread();
    router.push(`/workspaces/${workspaceId}/chat/new`);
  };

  const handleSelectThread = (thread: ThreadSummary) => {
    router.push(`/workspaces/${workspaceId}/chat/${thread.id}`);
  };

  const handleDeleteThread = async (threadId: string) => {
    setDeletingId(threadId);
    try {
      await deleteThread(threadId, workspaceId);
    } finally {
      setDeletingId(null);
    }
  };

  const handleGoToDashboard = () => {
    router.push(`/workspaces/${workspaceId}`);
  };

  if (collapsed) {
    return (
      <div className="flex h-full w-12 flex-col items-center border-r border-[var(--border-default)] bg-[var(--bg-surface)] py-3 gap-3">
        <button
          type="button"
          onClick={onToggleCollapse}
          className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={handleGoToDashboard}
          className={cn(
            "rounded-lg p-2 transition-colors",
            isDashboard
              ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
              : "text-[var(--text-muted)] hover:bg-[var(--bg-muted)]"
          )}
        >
          <LayoutDashboard className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={handleNewChat}
          className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full w-[240px] flex-col border-r border-[var(--border-default)] bg-[var(--bg-surface)]">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-3 border-b border-[var(--border-default)]">
        <span className="text-sm font-semibold text-[var(--text-primary)] truncate">
          {workspaces.find((ws) => ws.id === workspaceId)?.name ?? "Workspace"}
        </span>
        <button
          type="button"
          onClick={onToggleCollapse}
          className="rounded-lg p-1.5 text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
      </div>

      {/* View Switcher */}
      <div className="px-3 py-2 space-y-1">
        <button
          type="button"
          onClick={handleGoToDashboard}
          className={cn(
            "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
            isDashboard
              ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] font-medium"
              : "text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]"
          )}
        >
          <LayoutDashboard className="h-4 w-4" />
          Dashboard
        </button>
      </div>

      {/* New Chat Button */}
      <div className="px-3 py-2">
        <button
          type="button"
          onClick={handleNewChat}
          className="flex w-full items-center gap-2 rounded-lg border border-dashed border-[var(--border-default)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:border-[var(--accent-primary)] hover:text-[var(--accent-primary)] transition-colors"
        >
          <Plus className="h-4 w-4" />
          New Chat
        </button>
      </div>

      {/* Thread List */}
      <div className="flex-1 overflow-y-auto px-3 py-1">
        <p className="px-1 pb-2 text-[11px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
          Conversations
        </p>
        {isThreadsLoading ? (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-4 w-4 animate-spin text-[var(--text-muted)]" />
          </div>
        ) : threads.length === 0 ? (
          <p className="px-1 py-2 text-xs text-[var(--text-muted)]">
            No conversations yet
          </p>
        ) : (
          <div className="space-y-0.5">
            {threads.map((thread) => (
              <div
                key={thread.id}
                className={cn(
                  "group flex items-center rounded-lg transition-colors",
                  activeThreadId === thread.id && isChatView
                    ? "bg-[var(--accent-primary)]/10"
                    : "hover:bg-[var(--bg-muted)]"
                )}
              >
                <button
                  type="button"
                  onClick={() => handleSelectThread(thread)}
                  className="flex-1 min-w-0 flex items-center gap-2 px-2 py-2 text-left"
                >
                  <MessageSquare className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" />
                  <span className="truncate text-sm text-[var(--text-primary)]">
                    {thread.title || "New Chat"}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => void handleDeleteThread(thread.id)}
                  disabled={deletingId === thread.id}
                  className="mr-1 rounded p-1 opacity-0 group-hover:opacity-100 text-[var(--text-muted)] hover:text-red-500 transition-all disabled:opacity-50"
                >
                  {deletingId === thread.id ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5" />
                  )}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Workspace Selector */}
      <div className="border-t border-[var(--border-default)] px-3 py-2">
        <button
          type="button"
          onClick={() => router.push("/workspaces")}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-muted)] transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
          All Workspaces
        </button>
      </div>
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd /home/cjz/wenjin/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors related to AppShellSidebar

**Step 3: Commit**

```bash
git add frontend/components/workspace/AppShellSidebar.tsx
git commit -m "feat(frontend): add AppShellSidebar component for chat-centric layout"
```

---

### Task 2: Update Workbench Layout to Use AppShell

Replace the current bare layout in `app/(workbench)/workspaces/[id]/layout.tsx` with an AppShell that includes the sidebar.

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/layout.tsx`

**Step 1: Update the layout**

Replace the entire content of `frontend/app/(workbench)/workspaces/[id]/layout.tsx` with:

```tsx
"use client";

import { ReactNode, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useWorkspaceEventStream } from "@/hooks/useWorkspaceEventStream";
import { useFeaturesStore } from "@/stores/features";
import { useChatStore } from "@/stores/chat";
import { useWorkspaceStore } from "@/stores/workspace";
import { CommandPalette } from "@/components/workspace/CommandPalette";
import { AppShellSidebar } from "@/components/workspace/AppShellSidebar";

interface WorkbenchLayoutProps {
  children: ReactNode;
  params: Promise<{ id: string }>;
}

export default function WorkbenchLayout({ children }: WorkbenchLayoutProps) {
  const params = useParams();
  const workspaceId = params.id as string;
  useWorkspaceEventStream(workspaceId || null);
  const { loadWorkspace, fetchArtifacts, fetchActivity, clearWorkspace } = useWorkspaceStore();
  const { fetchFeatures, clearFeatures } = useFeaturesStore();
  const { loadLatestThread, clearMessages } = useChatStore();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useEffect(() => {
    if (!workspaceId) {
      return;
    }

    void loadWorkspace(workspaceId);
    void fetchFeatures(workspaceId);
    void fetchArtifacts(workspaceId);
    void fetchActivity(workspaceId);
    void loadLatestThread(workspaceId);

    return () => {
      clearWorkspace();
      clearFeatures();
      clearMessages();
    };
  }, [
    workspaceId,
    loadWorkspace,
    fetchFeatures,
    fetchArtifacts,
    fetchActivity,
    loadLatestThread,
    clearWorkspace,
    clearFeatures,
    clearMessages,
  ]);

  return (
    <div className="h-screen flex bg-[var(--bg-base)]">
      <AppShellSidebar
        workspaceId={workspaceId}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
      />
      <div className="flex-1 flex flex-col min-w-0">
        {children}
      </div>
      <CommandPalette workspaceId={workspaceId} />
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd /home/cjz/wenjin/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/app/(workbench)/workspaces/[id]/layout.tsx
git commit -m "feat(frontend): integrate AppShellSidebar into workbench layout"
```

---

### Task 3: Redesign Dashboard Page

Simplify the workspace main page: remove TaskTrack (linear workflow), remove module status overview, add flat feature cards that navigate to chat, add running tasks section, add recent conversations.

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/page.tsx`

**Step 1: Rewrite the Dashboard page**

Replace the entire content of `frontend/app/(workbench)/workspaces/[id]/page.tsx` with:

```tsx
"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2, MessageSquare, Play, ExternalLink } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeaturesStore } from "@/stores/features";
import { useChatStore } from "@/stores/chat";
import { useDashboardStore } from "@/stores/dashboard";
import { RecentArtifacts } from "./components/RecentArtifacts";
import { cn } from "@/lib/utils";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import type { WorkspaceFeature, ThreadSummary } from "@/lib/api";

const RECENT_ARTIFACTS_LIMIT = 5;

const workspaceTypeLabels: Record<string, string> = {
  sci: "学术论文",
  thesis: "学位论文",
  proposal: "研究计划",
  software_copyright: "软件著作权申请",
  patent: "专利申请",
};

const workspaceTypeColors: Record<string, string> = {
  sci: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  thesis: "bg-purple-500/10 text-purple-600 dark:text-purple-400",
  proposal: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  software_copyright: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
  patent: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
};

/** Feature icon mapping from registry icon strings to emoji for now. */
const featureIconMap: Record<string, string> = {
  microscope: "🔬",
  book_open: "📖",
  file_text: "📝",
  pen_tool: "✍️",
  image: "📈",
  package: "📦",
  search: "🔍",
  eye: "👁️",
  edit_3: "✏️",
  git_branch: "🔀",
  clipboard: "📋",
  zap: "⚡",
  compass: "🧭",
  flask: "🧪",
  shield: "🛡️",
  star: "⭐",
};

function getFeatureEmoji(icon: string | undefined): string {
  return featureIconMap[icon ?? ""] ?? "📋";
}

interface FeatureCardProps {
  feature: WorkspaceFeature;
  workspaceId: string;
}

function FeatureCard({ feature, workspaceId }: FeatureCardProps) {
  const router = useRouter();

  const handleClick = () => {
    // Navigate to chat with skill pre-selected
    // Map feature.id to the chat skill id format (underscores to hyphens)
    const skillId = feature.id.replace(/_/g, "-");
    router.push(`/workspaces/${workspaceId}/chat/new?skill=${skillId}`);
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className={cn(
        "flex flex-col items-start gap-2 rounded-xl border px-4 py-4 text-left transition-all",
        "border-[var(--border-default)] bg-[var(--bg-elevated)]",
        "hover:border-[var(--accent-primary)]/30 hover:shadow-sm hover:bg-[var(--bg-surface)]"
      )}
    >
      <div className="flex items-center gap-3 w-full">
        <span className="text-xl">{getFeatureEmoji(feature.icon)}</span>
        <p className="text-sm font-medium text-[var(--text-primary)] truncate flex-1">
          {feature.name}
        </p>
        <ExternalLink className="h-3.5 w-3.5 text-[var(--text-muted)] opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
      <p className="text-xs text-[var(--text-muted)] line-clamp-2 leading-relaxed">
        {feature.description}
      </p>
    </button>
  );
}

interface ActiveTaskCardProps {
  task: {
    task_id: string;
    task_type: string;
    status: string;
    progress: number;
    message: string | null;
    feature_id?: string;
  };
  workspaceId: string;
}

function ActiveTaskCard({ task, workspaceId }: ActiveTaskCardProps) {
  const router = useRouter();

  return (
    <button
      type="button"
      onClick={() => router.push(`/workspaces/${workspaceId}/chat/new`)}
      className="flex items-center gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 w-full text-left transition-colors hover:bg-amber-500/10"
    >
      <Loader2 className="h-4 w-4 animate-spin text-amber-500 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-[var(--text-primary)] truncate">
          {task.message || task.task_type}
        </p>
        <div className="mt-1 h-1.5 w-full rounded-full bg-[var(--bg-muted)]">
          <div
            className="h-full rounded-full bg-amber-500 transition-all duration-300"
            style={{ width: `${Math.min(100, task.progress)}%` }}
          />
        </div>
      </div>
      <span className="text-xs font-medium text-amber-600 shrink-0">
        {task.progress}%
      </span>
    </button>
  );
}

interface RecentThreadProps {
  thread: ThreadSummary;
  workspaceId: string;
}

function RecentThread({ thread, workspaceId }: RecentThreadProps) {
  const router = useRouter();

  return (
    <button
      type="button"
      onClick={() => router.push(`/workspaces/${workspaceId}/chat/${thread.id}`)}
      className="flex items-center gap-3 rounded-lg px-3 py-2 w-full text-left transition-colors hover:bg-[var(--bg-muted)]"
    >
      <MessageSquare className="h-4 w-4 shrink-0 text-[var(--text-muted)]" />
      <span className="text-sm text-[var(--text-primary)] truncate flex-1">
        {thread.title || "New Chat"}
      </span>
      <span className="text-[11px] text-[var(--text-muted)] shrink-0">
        {new Date(thread.updated_at).toLocaleDateString()}
      </span>
    </button>
  );
}

export default function WorkspaceDashboard() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;

  const { workspace, isWorkspaceLoading, error, artifacts } = useWorkspaceStore();
  const { features } = useFeaturesStore();
  const { threads } = useChatStore();
  const { modules, fetchDashboard, reset: resetDashboard } = useDashboardStore();

  useEffect(() => {
    if (workspaceId) {
      void fetchDashboard(workspaceId);
    }
    return () => {
      resetDashboard();
    };
  }, [workspaceId, fetchDashboard, resetDashboard]);

  // Derive active tasks from dashboard modules
  const activeTasks = modules
    .filter((m) => m.status === "in_progress")
    .map((m) => ({
      task_id: m.id,
      task_type: m.id,
      status: "running",
      progress: 50, // Dashboard modules don't have precise progress
      message: features.find((f) => f.id === m.id)?.name ?? m.id,
      feature_id: m.id,
    }));

  const recentThreads = threads.slice(0, 5);

  if (isWorkspaceLoading || (!workspace && !error)) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col items-center gap-4"
        >
          <Loader2 className="w-8 h-8 text-academic-primary animate-spin" />
          <p className="text-slate-500 dark:text-slate-400">Loading workspace...</p>
        </motion.div>
      </div>
    );
  }

  if (error || !workspace) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center"
        >
          <p className="text-red-500 mb-4">{error || "Workspace not found"}</p>
          <button
            onClick={() => router.push("/workspaces")}
            className="px-4 py-2 rounded-lg bg-academic-primary text-white hover:bg-academic-primary/90 transition-colors"
          >
            Back to Workspaces
          </button>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-default)] bg-[var(--glass-bg)] backdrop-blur-xl">
        <div>
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">
            {workspace.name}
          </h1>
          {workspace.description && (
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              {workspace.description}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span
            className={cn(
              "px-3 py-1 rounded-full text-xs font-medium",
              workspaceTypeColors[workspace.type] || "bg-slate-500/10 text-slate-600"
            )}
          >
            {workspaceTypeLabels[workspace.type] || workspace.type}
          </span>
          {workspace.discipline && (
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-[var(--bg-surface)] text-[var(--text-secondary)] border border-[var(--border-default)]">
              {workspace.discipline}
            </span>
          )}
          <button
            type="button"
            onClick={() => router.push(`/workspaces/${workspaceId}/chat/new`)}
            className="flex items-center gap-2 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 transition-opacity"
          >
            <MessageSquare className="h-4 w-4" />
            Chat
          </button>
        </div>
      </header>

      {/* Main Content */}
      <ErrorBoundary>
        <main className="flex-1 overflow-auto p-6">
          <div className="max-w-5xl mx-auto space-y-8">
            {/* Active Tasks — Only shown when there are running tasks */}
            {activeTasks.length > 0 && (
              <section>
                <h2 className="text-sm font-medium text-[var(--text-muted)] mb-3">
                  Running Tasks
                </h2>
                <div className="space-y-2">
                  {activeTasks.map((task) => (
                    <ActiveTaskCard
                      key={task.task_id}
                      task={task}
                      workspaceId={workspaceId}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Feature Cards */}
            <section>
              <h2 className="text-sm font-medium text-[var(--text-muted)] mb-3">
                Features
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {features.map((feature) => (
                  <FeatureCard
                    key={feature.id}
                    feature={feature}
                    workspaceId={workspaceId}
                  />
                ))}
              </div>
            </section>

            {/* Bottom Row: Recent Conversations + Recent Artifacts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Recent Conversations */}
              <section>
                <h2 className="text-sm font-medium text-[var(--text-muted)] mb-3">
                  Recent Conversations
                </h2>
                <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-3">
                  {recentThreads.length === 0 ? (
                    <p className="py-4 text-center text-sm text-[var(--text-muted)]">
                      No conversations yet. Start a chat to begin.
                    </p>
                  ) : (
                    <div className="space-y-0.5">
                      {recentThreads.map((thread) => (
                        <RecentThread
                          key={thread.id}
                          thread={thread}
                          workspaceId={workspaceId}
                        />
                      ))}
                    </div>
                  )}
                </div>
              </section>

              {/* Recent Artifacts */}
              <section>
                <h2 className="text-sm font-medium text-[var(--text-muted)] mb-3">
                  Recent Artifacts
                </h2>
                <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
                  <RecentArtifacts
                    artifacts={artifacts.slice(0, RECENT_ARTIFACTS_LIMIT)}
                  />
                </div>
              </section>
            </div>
          </div>
        </main>
      </ErrorBoundary>
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd /home/cjz/wenjin/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/app/(workbench)/workspaces/[id]/page.tsx
git commit -m "feat(frontend): redesign dashboard — flat feature cards, no linear workflow"
```

---

### Task 4: Create Full-Screen Chat Route

Create the dedicated `/workspaces/[id]/chat/[threadId]` route that renders the existing ChatPanel in full-screen mode. The `threadId` can be "new" for a fresh thread or an actual thread ID.

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/chat/[threadId]/page.tsx`

**Step 1: Create the chat route page**

```tsx
// frontend/app/(workbench)/workspaces/[id]/chat/[threadId]/page.tsx
"use client";

import { useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useChatStore } from "@/stores/chat";
import { ChatPanel } from "../../components/ChatPanel";

export default function ChatViewPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const threadId = params.threadId as string;
  const skillFromUrl = searchParams.get("skill");

  const { loadThread, startNewThread, setCurrentSkill, threadId: currentThreadId } = useChatStore();

  useEffect(() => {
    if (threadId === "new") {
      // Only start a new thread if we're not already on one
      if (currentThreadId !== null) {
        startNewThread();
      }
      if (skillFromUrl) {
        setCurrentSkill(skillFromUrl);
      }
    } else if (threadId && threadId !== currentThreadId) {
      void loadThread(threadId);
    }
  }, [threadId, skillFromUrl, currentThreadId, loadThread, startNewThread, setCurrentSkill]);

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <ChatPanel workspaceId={workspaceId} />
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd /home/cjz/wenjin/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/app/(workbench)/workspaces/[id]/chat/
git commit -m "feat(frontend): add full-screen chat route /workspaces/[id]/chat/[threadId]"
```

---

### Task 5: Add Inline TaskCard to Chat Messages

Create a TaskCard component that renders inline in the chat message list to show task lifecycle (pending → running with progress → completed result). Integrate it into the existing WorkspaceChatMessages component.

**Files:**
- Create: `frontend/components/workspace/TaskCard.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/WorkspaceChatMessages.tsx` (import and render TaskCard for task-type messages)

**Step 1: Create the TaskCard component**

```tsx
// frontend/components/workspace/TaskCard.tsx
"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  Loader2,
  CheckCircle2,
  AlertCircle,
  Clock3,
  ChevronDown,
  ChevronUp,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";

type TaskCardStatus = "pending" | "running" | "success" | "failed" | "cancelled";

interface TaskCardProps {
  taskId: string;
  taskType: string;
  status: TaskCardStatus;
  progress: number;
  message: string | null;
  featureName?: string;
  result?: Record<string, unknown> | null;
  error?: string | null;
  onViewDetail?: () => void;
  className?: string;
}

const statusConfig: Record<
  TaskCardStatus,
  {
    icon: typeof Loader2;
    label: string;
    borderClass: string;
    bgClass: string;
    iconClass: string;
    animate?: boolean;
  }
> = {
  pending: {
    icon: Clock3,
    label: "Queued",
    borderClass: "border-slate-300/30",
    bgClass: "bg-slate-50 dark:bg-slate-900/20",
    iconClass: "text-slate-500",
  },
  running: {
    icon: Loader2,
    label: "Running",
    borderClass: "border-amber-500/30",
    bgClass: "bg-amber-50 dark:bg-amber-900/10",
    iconClass: "text-amber-500",
    animate: true,
  },
  success: {
    icon: CheckCircle2,
    label: "Completed",
    borderClass: "border-emerald-500/30",
    bgClass: "bg-emerald-50 dark:bg-emerald-900/10",
    iconClass: "text-emerald-500",
  },
  failed: {
    icon: AlertCircle,
    label: "Failed",
    borderClass: "border-red-500/30",
    bgClass: "bg-red-50 dark:bg-red-900/10",
    iconClass: "text-red-500",
  },
  cancelled: {
    icon: AlertCircle,
    label: "Cancelled",
    borderClass: "border-slate-400/30",
    bgClass: "bg-slate-50 dark:bg-slate-900/20",
    iconClass: "text-slate-400",
  },
};

export function TaskCard({
  taskId,
  taskType,
  status,
  progress,
  message,
  featureName,
  result,
  error,
  onViewDetail,
  className,
}: TaskCardProps) {
  const [expanded, setExpanded] = useState(false);
  const config = statusConfig[status] ?? statusConfig.pending;
  const Icon = config.icon;
  const displayName = featureName || taskType.replace(/_/g, " ");
  const isTerminal = status === "success" || status === "failed" || status === "cancelled";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "rounded-xl border px-4 py-3 my-2",
        config.borderClass,
        config.bgClass,
        className
      )}
    >
      {/* Header row */}
      <div className="flex items-center gap-3">
        <Icon
          className={cn(
            "h-5 w-5 shrink-0",
            config.iconClass,
            config.animate && "animate-spin"
          )}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium text-[var(--text-primary)] truncate">
              {displayName}
            </p>
            <span className="text-[11px] font-medium text-[var(--text-muted)]">
              {config.label}
            </span>
          </div>
          {message && (
            <p className="text-xs text-[var(--text-muted)] mt-0.5 truncate">
              {message}
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0">
          {onViewDetail && (
            <button
              type="button"
              onClick={onViewDetail}
              className="rounded-lg p-1.5 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
              title="View details"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </button>
          )}
          {isTerminal && (result || error) && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="rounded-lg p-1.5 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
            >
              {expanded ? (
                <ChevronUp className="h-3.5 w-3.5" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5" />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Progress bar (only for running) */}
      {status === "running" && (
        <div className="mt-2 h-1.5 w-full rounded-full bg-[var(--bg-muted)]">
          <motion.div
            className="h-full rounded-full bg-amber-500"
            initial={{ width: 0 }}
            animate={{ width: `${Math.min(100, progress)}%` }}
            transition={{ duration: 0.3 }}
          />
        </div>
      )}

      {/* Expanded content */}
      {expanded && error && (
        <div className="mt-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          {error}
        </div>
      )}
      {expanded && result && !error && (
        <div className="mt-3 rounded-lg bg-[var(--bg-muted)] px-3 py-2 text-xs text-[var(--text-secondary)] max-h-[200px] overflow-auto">
          <pre className="whitespace-pre-wrap break-words">
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}
    </motion.div>
  );
}
```

**Step 2: Read the current WorkspaceChatMessages to understand how to integrate TaskCard**

Read: `frontend/app/(workbench)/workspaces/[id]/components/WorkspaceChatMessages.tsx`

The implementer should look for where message blocks with `kind === "task"` or blocks that contain `task_id` are rendered. If the existing rendering already handles task blocks, skip integration. If not, add `<TaskCard>` rendering for messages that have `metadata.orchestration.task_id`.

The typical integration point is inside the message rendering loop, when processing assistant message blocks. For each block that has a task reference, render a `<TaskCard>` with the task status from the workspace event stream.

**Step 3: Verify it compiles**

Run: `cd /home/cjz/wenjin/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors related to TaskCard

**Step 4: Commit**

```bash
git add frontend/components/workspace/TaskCard.tsx
git commit -m "feat(frontend): add inline TaskCard component for chat task lifecycle display"
```

---

### Task 6: Create TaskDetailPanel Component

Build the expandable right panel that slides in when the user clicks "View details" on a TaskCard. This panel reuses rendering logic from the existing TaskRuntimePanel.

**Files:**
- Create: `frontend/components/workspace/TaskDetailPanel.tsx`

**Step 1: Create the TaskDetailPanel component**

```tsx
// frontend/components/workspace/TaskDetailPanel.tsx
"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { TaskRuntimePanel } from "./TaskRuntimePanel";
import type { TaskRuntimeState } from "@/lib/task-runtime";

interface TaskDetailPanelProps {
  open: boolean;
  onClose: () => void;
  taskId: string | null;
  runtime: TaskRuntimeState | null;
  status: string | null;
  error: string | null;
  title?: string;
}

export function TaskDetailPanel({
  open,
  onClose,
  taskId,
  runtime,
  status,
  error,
  title,
}: TaskDetailPanelProps) {
  const isRunning = status === "running" || status === "pending";

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 380, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ type: "spring", damping: 25, stiffness: 200 }}
          className="h-full border-l border-[var(--border-default)] bg-[var(--bg-surface)] overflow-hidden flex flex-col"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border-default)]">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-[var(--text-primary)] truncate">
                {title || "Task Details"}
              </p>
              {taskId && (
                <p className="text-[11px] text-[var(--text-muted)] truncate mt-0.5">
                  {taskId}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Content — delegate to existing TaskRuntimePanel */}
          <div className="flex-1 overflow-auto p-4">
            <TaskRuntimePanel
              runtime={runtime}
              isRunning={isRunning}
              status={status}
              error={error}
              title={title || "Task"}
              emptyTitle="No runtime data"
              emptyDescription="Task details will appear here when available."
            />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd /home/cjz/wenjin/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/components/workspace/TaskDetailPanel.tsx
git commit -m "feat(frontend): add TaskDetailPanel — expandable right panel for task runtime"
```

---

### Task 7: Add Feature Route Redirects

Create a catch-all redirect page that maps old feature routes (e.g., `/workspaces/[id]/deep-research`) to the new chat route with the corresponding skill pre-selected.

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/(feature-redirect)/[featureSlug]/page.tsx`
- Create: `frontend/lib/feature-redirect-map.ts`

**Step 1: Create the redirect mapping**

```tsx
// frontend/lib/feature-redirect-map.ts

/**
 * Maps old feature route slugs to chat skill IDs for redirect purposes.
 * Old: /workspaces/[id]/deep-research
 * New: /workspaces/[id]/chat/new?skill=deep-research
 */
export const featureSlugToSkillId: Record<string, string> = {
  "deep-research": "deep-research",
  literature: "literature-management",
  "opening-research": "opening-research",
  "thesis-writing": "fullpaper-writer",
  "figure-generation": "figure-generation",
  "compile-export": "compile-export",
  "literature-search": "deep-research",
  "paper-analysis": "paper-analysis",
  writing: "writing",
  "literature-review": "literature-review",
  "framework-outline": "framework-designer",
  "peer-review": "peer-reviewer",
  "journal-recommend": "journal-recommender",
  "proposal-outline": "proposal-writer",
  "background-research": "background-research",
  "experiment-design": "experiment-designer",
  "copyright-materials": "copyright-materials",
  "technical-description": "technical-description",
  "patent-outline": "patent-outline",
  "prior-art-search": "prior-art-search",
};
```

**Step 2: Create the redirect page**

Note: The implementer should check if Next.js route groups `(feature-redirect)` work alongside the existing feature pages. If the old feature page files still exist at build time, they will take precedence. The redirect page should be created AFTER removing the old feature pages in Task 8. Alternatively, the implementer can update each existing feature page to redirect instead.

A simpler approach: create a Next.js middleware that matches old feature routes and redirects.

Create `frontend/middleware.ts` (or modify if it exists):

```tsx
// frontend/middleware.ts
import { NextRequest, NextResponse } from "next/server";
import { featureSlugToSkillId } from "@/lib/feature-redirect-map";

const FEATURE_ROUTE_RE = /^\/workspaces\/([^/]+)\/([^/]+)$/;

export function middleware(request: NextRequest) {
  const match = request.nextUrl.pathname.match(FEATURE_ROUTE_RE);
  if (!match) {
    return NextResponse.next();
  }

  const [, workspaceId, slug] = match;
  const skillId = featureSlugToSkillId[slug];

  // Only redirect known feature slugs, not "chat" or other valid routes
  if (!skillId) {
    return NextResponse.next();
  }

  const url = request.nextUrl.clone();
  url.pathname = `/workspaces/${workspaceId}/chat/new`;
  url.searchParams.set("skill", skillId);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: "/workspaces/:id/:slug",
};
```

**Step 3: Verify it compiles**

Run: `cd /home/cjz/wenjin/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/lib/feature-redirect-map.ts frontend/middleware.ts
git commit -m "feat(frontend): add feature route redirects to chat-centric routes"
```

---

### Task 8: Remove Old Feature Pages

Delete the 20 individual feature page directories since they are now handled by the redirect middleware + chat view.

**Files:**
- Delete: `frontend/app/(workbench)/workspaces/[id]/deep-research/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/literature/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/opening-research/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/thesis-writing/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/figure-generation/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/compile-export/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/literature-search/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/paper-analysis/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/writing/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/literature-review/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/framework-outline/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/peer-review/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/journal-recommend/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/proposal-outline/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/background-research/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/experiment-design/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/copyright-materials/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/technical-description/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/patent-outline/`
- Delete: `frontend/app/(workbench)/workspaces/[id]/prior-art-search/`

**Step 1: Verify no other files import from these pages**

Run: `grep -r "from.*/(deep-research|literature-search|thesis-writing)" frontend/app/ frontend/components/ frontend/stores/ frontend/lib/ --include="*.tsx" --include="*.ts" | grep -v node_modules | head -20`

If any non-page files import from these directories, update those imports first.

**Step 2: Delete the feature page directories**

```bash
cd /home/cjz/wenjin/frontend
FEATURE_DIRS=(
  deep-research literature opening-research thesis-writing
  figure-generation compile-export literature-search paper-analysis
  writing literature-review framework-outline peer-review
  journal-recommend proposal-outline background-research
  experiment-design copyright-materials technical-description
  patent-outline prior-art-search
)
for dir in "${FEATURE_DIRS[@]}"; do
  rm -rf "app/(workbench)/workspaces/[id]/$dir"
done
```

**Step 3: Verify the app still builds**

Run: `cd /home/cjz/wenjin/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors (old pages were self-contained)

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor(frontend): remove 20 old feature page routes (replaced by chat + redirect)"
```

---

### Task 9: Clean Up Unused Stores and Utilities

Remove stores and utilities that are no longer needed after the feature pages are gone.

**Files:**
- Potentially remove: `frontend/stores/thesis-writing.ts` (if no remaining consumers)
- Potentially remove: `frontend/lib/workspace-feature-routes.ts` (route map no longer used for navigation — but check if still used elsewhere)
- Modify: `frontend/stores/index.ts` (remove re-exports of deleted stores)

**Step 1: Check for remaining consumers**

Run: `grep -r "useThesisWritingStore\|thesis-writing" frontend/ --include="*.ts" --include="*.tsx" | grep -v node_modules | grep -v "stores/thesis-writing.ts"`

Run: `grep -r "workspaceFeatureRouteMap\|getWorkspaceFeatureRoute" frontend/ --include="*.ts" --include="*.tsx" | grep -v node_modules | grep -v "workspace-feature-routes.ts"`

**Step 2: Delete files with zero remaining consumers**

Only delete if grep shows no results. If files are still imported elsewhere, leave them for now.

**Step 3: Verify the app still compiles**

Run: `cd /home/cjz/wenjin/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor(frontend): remove unused stores and utilities after feature page cleanup"
```

---

### Task 10: Backend — Add GET /workspaces/:id/features Endpoint (if missing)

Verify the backend features endpoint exists. Based on exploration, `GET /api/workspaces/{workspace_id}/features` already exists at `src/gateway/routers/features.py`. If it works correctly, this task is a no-op. If not, create/fix it.

**Files:**
- Check: `backend/src/gateway/routers/features.py`
- Test: `backend/tests/gateway/routers/test_features.py` (if endpoint needs changes)

**Step 1: Verify the endpoint exists and is registered**

Run: `grep -r "features" backend/src/gateway/routers/ --include="*.py" -l`
Run: `grep -r "include_router.*feature" backend/src/gateway/ --include="*.py"`

If the endpoint exists and is registered on the gateway app, this task is done.

**Step 2: Test the endpoint**

Run: `cd /home/cjz/wenjin/backend && python -c "from src.gateway.routers.features import router; print('OK')"`

If this prints OK, the endpoint is importable and task is complete.

**Step 3: Commit (only if changes were needed)**

```bash
git add backend/
git commit -m "feat(backend): ensure GET /workspaces/:id/features endpoint is available"
```

---

### Task 11: Integration Testing — Verify Full Flow

Manually verify the end-to-end flow works by building the frontend and checking key interactions.

**Step 1: Build the frontend**

Run: `cd /home/cjz/wenjin/frontend && npm run build 2>&1 | tail -20`
Expected: Build succeeds

**Step 2: Verify routes exist**

Check that these routes are in the build output:
- `/workspaces` (list)
- `/workspaces/[id]` (dashboard)
- `/workspaces/[id]/chat/[threadId]` (chat view)

**Step 3: Verify old routes redirect**

Check that middleware is compiled:
Run: `ls -la /home/cjz/wenjin/frontend/.next/server/middleware*`

**Step 4: Commit final integration**

```bash
git add -A
git commit -m "chore(frontend): verify frontend build after chat-centric redesign"
```
