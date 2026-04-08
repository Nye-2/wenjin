# Workspace UX Simplification Implementation Plan

> 归档说明: 本文档为历史阶段性计划快照，可能包含已过时路由、线程模型或状态描述。当前实现请以 `docs/product/workspace-current-state.md` 与相关当前契约文档为准。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Simplify the workspace post-entry experience by slimming the dashboard, replacing the feature parameter form with conversational guidance, redesigning the sidebar, and adding new-workspace onboarding auto-redirect.

**Architecture:** Frontend-only changes. Feature cards route directly to chat instead of the parameter form page. The sidebar becomes a compact stepper + thread list. New workspaces auto-redirect to chat with an onboarding entry prompt. All changes are in Next.js React components and route utilities.

**Tech Stack:** Next.js 16, React 19, TypeScript, Zustand, TailwindCSS, Framer Motion

---

### Task 1: Add feature-to-stage mapping data

This is a prerequisite for grouping feature cards by stage on the dashboard.

**Files:**
- Create: `frontend/lib/workspace-feature-stages.ts`

**Step 1: Create the stage mapping module**

```typescript
// frontend/lib/workspace-feature-stages.ts

export interface WorkspaceStage {
  id: string;
  title: string;
  description: string;
}

export const workspaceStages: WorkspaceStage[] = [
  { id: "research", title: "背景调研", description: "明确问题边界与任务目标" },
  { id: "collection", title: "资料收集", description: "把来源、文献与证据放进同一条线" },
  { id: "structure", title: "结构设计", description: "组织论证路径与章节框架" },
  { id: "writing", title: "写作修订", description: "持续推进正文、申报文本与说明材料" },
  { id: "review", title: "评审交付", description: "整理输出、检查清单并完成交付" },
];

/**
 * Maps each feature ID to a stage ID.
 * Features not listed here default to the first stage.
 */
export const featureStageMap: Record<string, string> = {
  // Stage: research
  deep_research: "research",
  background_research: "research",
  opening_research: "research",
  prior_art_search: "research",
  literature_search: "research",

  // Stage: collection
  literature_management: "collection",
  literature_review: "collection",
  paper_analysis: "collection",

  // Stage: structure
  framework_outline: "structure",
  proposal_outline: "structure",
  patent_outline: "structure",
  experiment_design: "structure",

  // Stage: writing
  thesis_writing: "writing",
  writing: "writing",
  figure_generation: "writing",
  copyright_materials: "writing",
  technical_description: "writing",

  // Stage: review
  peer_review: "review",
  journal_recommend: "review",
  compile_export: "review",
};

export function getFeatureStageId(featureId: string): string {
  return featureStageMap[featureId] ?? "research";
}

export function getStageById(stageId: string): WorkspaceStage | undefined {
  return workspaceStages.find((s) => s.id === stageId);
}
```

**Step 2: Commit**

```bash
git add frontend/lib/workspace-feature-stages.ts
git commit -m "feat: add feature-to-stage mapping for grouped dashboard display"
```

---

### Task 2: Update route functions to point features directly to chat

**Files:**
- Modify: `frontend/lib/workspace-feature-routes.ts`

**Step 1: Make `getWorkspaceFeatureRoute` return chat route**

Replace the body of `getWorkspaceFeatureRoute` so it delegates to `getWorkspaceFeatureChatRoute`. This is the single change that redirects all feature card clicks to chat.

```typescript
// In workspace-feature-routes.ts, replace getWorkspaceFeatureRoute body:

export function getWorkspaceFeatureRoute(
  workspaceId: string,
  featureId: string | null | undefined,
  params?: Record<string, RouteParamValue>
): string | null {
  // Route directly to chat instead of the feature parameter page
  return getWorkspaceFeatureChatRoute(workspaceId, featureId, params);
}
```

Keep `getWorkspaceFeatureChatRoute` unchanged — it already builds the correct `/chat/new?feature=...&skill=...` URL.

**Step 2: Commit**

```bash
git add frontend/lib/workspace-feature-routes.ts
git commit -m "feat: route feature cards directly to chat, bypassing parameter form"
```

---

### Task 3: Convert feature page to redirect

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/features/[featureId]/page.tsx`

**Step 1: Replace the entire feature page with a redirect component**

Replace the full file content with a slim redirect:

```typescript
"use client";

import { useEffect } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { getWorkspaceFeatureChatRoute } from "@/lib/workspace-feature-routes";

export default function WorkspaceFeatureRedirect() {
  const router = useRouter();
  const params = useParams<{ id: string; featureId: string }>();
  const searchParams = useSearchParams();
  const workspaceId = params.id;
  const featureId = params.featureId;

  useEffect(() => {
    const queryParams: Record<string, string> = {};
    searchParams.forEach((value, key) => {
      if (key !== "feature" && key !== "skill") {
        queryParams[key] = value;
      }
    });

    const chatRoute = getWorkspaceFeatureChatRoute(workspaceId, featureId, queryParams);
    if (chatRoute) {
      router.replace(chatRoute);
    } else {
      router.replace(`/workspaces/${workspaceId}`);
    }
  }, [router, workspaceId, featureId, searchParams]);

  return (
    <div className="flex h-full items-center justify-center bg-[var(--bg-base)]">
      <Loader2 className="h-6 w-6 animate-spin text-[var(--accent-primary)]" />
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/features/\[featureId\]/page.tsx
git commit -m "feat: convert feature page to redirect for backward compatibility"
```

---

### Task 4: Redesign the sidebar (AppShellSidebar)

**Files:**
- Modify: `frontend/components/workspace/AppShellSidebar.tsx`

**Step 1: Rewrite the expanded sidebar**

Key changes:
1. **Workspace info section** — remove brand text (`问津 / Wenjin`), remove description, keep only name + type/discipline tags
2. **Stage stepper** — replace verbose stage cards with compact single-line clickable stepper (dot + title, no descriptions)
3. **Work entries** — replace verbose buttons with two compact buttons: "新对话" and "工作总览"
4. **Thread list** — unchanged, benefits from reclaimed space

Replace the full component. The collapsed state stays the same.

```typescript
"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  FileText,
  LayoutDashboard,
  Loader2,
  MessageSquare,
  Plus,
  Trash2,
} from "lucide-react";
import { useChatStore } from "@/stores/chat";
import { useWorkspaceStore } from "@/stores/workspace";
import { useI18n } from "@/components/i18n-provider";
import { cn } from "@/lib/utils";
import { workspaceStages } from "@/lib/workspace-feature-stages";
import type { ThreadSummary } from "@/lib/api";

interface AppShellSidebarProps {
  workspaceId: string;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

function inferSuggestedStageIndex({
  pathname,
  threadsCount,
  artifactsCount,
}: {
  pathname: string;
  threadsCount: number;
  artifactsCount: number;
}) {
  if (pathname.includes("/chat/")) return 3;
  if (artifactsCount > 0) return 2;
  if (threadsCount > 0) return 1;
  return 0;
}

export function AppShellSidebar({
  workspaceId,
  collapsed = false,
  onToggleCollapse,
}: AppShellSidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { t } = useI18n();

  const threads = useChatStore((state) => state.threads);
  const activeThreadId = useChatStore((state) => state.threadId);
  const isThreadsLoading = useChatStore((state) => state.isThreadsLoading);
  const startNewThread = useChatStore((state) => state.startNewThread);
  const deleteThread = useChatStore((state) => state.deleteThread);

  const workspace = useWorkspaceStore((state) => state.workspace);
  const artifacts = useWorkspaceStore((state) => state.artifacts);
  const workspaces = useWorkspaceStore((state) => state.workspaces);

  const isOnChat = pathname.includes("/chat/");
  const isOnDashboard = pathname === `/workspaces/${workspaceId}`;

  const workspaceSnapshot =
    workspace ?? workspaces.find((c) => c.id === workspaceId) ?? null;
  const workspaceName = workspaceSnapshot?.name ?? "Workspace";
  const workspaceTypeLabel = workspaceSnapshot?.type
    ? t(`workspace.types.${workspaceSnapshot.type}`)
    : "";
  const disciplineLabel = workspaceSnapshot?.discipline
    ? workspaceSnapshot.discipline.replace(/_/g, " ")
    : null;

  const suggestedStageIndex = inferSuggestedStageIndex({
    pathname,
    threadsCount: threads.length,
    artifactsCount: artifacts.length,
  });

  const goToDashboard = () => router.push(`/workspaces/${workspaceId}`);
  const goToNewChat = () => {
    startNewThread();
    router.push(`/workspaces/${workspaceId}/chat/new`);
  };
  const goToThread = (threadId: string) =>
    router.push(`/workspaces/${workspaceId}/chat/${threadId}`);
  const handleDeleteThread = (event: React.MouseEvent, threadId: string) => {
    event.stopPropagation();
    void deleteThread(threadId, workspaceId);
  };
  const handleStageClick = (stageIndex: number) => {
    if (isOnDashboard) {
      const el = document.getElementById(`stage-${workspaceStages[stageIndex].id}`);
      el?.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      router.push(`/workspaces/${workspaceId}#stage-${workspaceStages[stageIndex].id}`);
    }
  };

  if (collapsed) {
    return (
      <aside className="flex w-14 shrink-0 flex-col items-center gap-2 border-r border-[var(--border-default)] bg-[rgba(251,248,242,0.92)] py-3">
        <button
          onClick={onToggleCollapse}
          className="rounded-xl p-2 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface)]"
          title="Expand sidebar"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
        <button
          onClick={goToDashboard}
          className={cn(
            "rounded-xl p-2 transition-colors",
            isOnDashboard
              ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
              : "text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
          )}
          title="工作总览"
        >
          <LayoutDashboard className="h-4 w-4" />
        </button>
        <button
          onClick={goToNewChat}
          className={cn(
            "rounded-xl border border-dashed border-[var(--border-default)] p-2 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface)]",
            isOnChat && "border-[var(--accent-primary)]/30 text-[var(--accent-primary)]"
          )}
          title="新对话"
        >
          <Plus className="h-4 w-4" />
        </button>
        <button
          onClick={() => router.push("/workspaces")}
          className="mt-auto rounded-xl p-2 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface)]"
          title="全部 workspace"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
      </aside>
    );
  }

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-[var(--border-default)] bg-[rgba(251,248,242,0.94)]">
      {/* Workspace info — compact */}
      <div className="border-b border-[var(--border-default)] px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-[var(--text-primary)]">
              {workspaceName}
            </h2>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {workspaceTypeLabel && (
                <span className="rounded-full border border-[var(--border-default)] bg-white/78 px-2.5 py-0.5 text-[11px] font-medium text-[var(--text-primary)]">
                  {workspaceTypeLabel}
                </span>
              )}
              {disciplineLabel && (
                <span className="rounded-full border border-[var(--border-default)] bg-[var(--bg-surface)] px-2.5 py-0.5 text-[11px] text-[var(--text-secondary)]">
                  {disciplineLabel}
                </span>
              )}
            </div>
          </div>
          <button
            onClick={onToggleCollapse}
            className="rounded-xl p-1.5 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface)]"
            title="Collapse sidebar"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Stage stepper — compact, clickable */}
      <div className="border-b border-[var(--border-default)] px-4 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
          工作阶段
        </p>
        <div className="mt-2.5 space-y-1">
          {workspaceStages.map((stage, index) => {
            const isCurrent = index === suggestedStageIndex;
            const isPast = index < suggestedStageIndex;
            return (
              <button
                key={stage.id}
                type="button"
                onClick={() => handleStageClick(index)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-xl px-2.5 py-1.5 text-left transition-colors hover:bg-[var(--bg-surface)]",
                  isCurrent && "bg-[rgba(166,124,57,0.06)]"
                )}
              >
                <div
                  className={cn(
                    "h-2.5 w-2.5 shrink-0 rounded-full border",
                    isCurrent
                      ? "border-[var(--brand-brass)] bg-[var(--brand-brass)]"
                      : isPast
                        ? "border-[var(--brand-teal)] bg-[var(--brand-teal)]"
                        : "border-[var(--border-default)] bg-white"
                  )}
                />
                <span
                  className={cn(
                    "text-sm",
                    isCurrent
                      ? "font-medium text-[var(--text-primary)]"
                      : isPast
                        ? "text-[var(--text-secondary)]"
                        : "text-[var(--text-muted)]"
                  )}
                >
                  {stage.title}
                </span>
                {isCurrent && (
                  <span className="ml-auto rounded-full bg-[rgba(166,124,57,0.1)] px-1.5 py-0.5 text-[9px] font-medium text-[var(--brand-brass)]">
                    当前
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Work entries — compact */}
      <div className="border-b border-[var(--border-default)] px-4 py-3">
        <div className="flex gap-2">
          <button
            onClick={goToNewChat}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-medium transition-colors",
              isOnChat
                ? "border-[var(--accent-primary)]/30 bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
                : "border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
            )}
          >
            <Plus className="h-3.5 w-3.5" />
            新对话
          </button>
          <button
            onClick={goToDashboard}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-medium transition-colors",
              isOnDashboard
                ? "border-[var(--accent-primary)]/30 bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
                : "border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
            )}
          >
            <LayoutDashboard className="h-3.5 w-3.5" />
            总览
          </button>
        </div>
      </div>

      {/* Thread list */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
            对话记录
          </p>
          <button
            onClick={goToNewChat}
            className="rounded-lg border border-[var(--border-default)] bg-white/80 p-1.5 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface)]"
            title="新建对话"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>

        {isThreadsLoading ? (
          <div className="flex items-center justify-center py-8 text-[var(--text-muted)]">
            <Loader2 className="h-4 w-4 animate-spin" />
          </div>
        ) : threads.length === 0 ? (
          <div className="rounded-xl border border-[var(--border-default)] bg-white/70 px-3 py-5 text-center">
            <MessageSquare className="mx-auto h-5 w-5 text-[var(--text-muted)]" />
            <p className="mt-2 text-xs text-[var(--text-secondary)]">
              还没有对话记录
            </p>
          </div>
        ) : (
          <ul className="space-y-1.5">
            {threads.map((thread: ThreadSummary) => {
              const isActive = isOnChat && thread.id === activeThreadId;
              return (
                <li key={thread.id}>
                  <div
                    className={cn(
                      "group flex items-start gap-2 rounded-xl border px-2.5 py-2 transition-colors",
                      isActive
                        ? "border-[var(--accent-primary)]/20 bg-[var(--accent-primary)]/10"
                        : "border-[var(--border-default)] bg-white/72 hover:bg-[var(--bg-surface)]"
                    )}
                  >
                    <button
                      onClick={() => goToThread(thread.id)}
                      className="flex min-w-0 flex-1 items-start gap-2 text-left"
                    >
                      <div className="mt-0.5 rounded-lg bg-[var(--bg-surface)] p-1.5">
                        <FileText className="h-3.5 w-3.5 text-[var(--text-muted)]" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p
                          className={cn(
                            "truncate text-sm font-medium",
                            isActive ? "text-[var(--accent-primary)]" : "text-[var(--text-primary)]"
                          )}
                        >
                          {thread.title || "未命名对话"}
                        </p>
                        <p className="mt-0.5 line-clamp-1 text-[11px] leading-5 text-[var(--text-muted)]">
                          {thread.last_message_preview || "点击继续"}
                        </p>
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={(event) => handleDeleteThread(event, thread.id)}
                      className="ml-auto rounded-md p-1 text-[var(--text-muted)] opacity-0 transition-all hover:bg-red-500/10 hover:text-red-500 group-hover:opacity-100"
                      title="删除"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Back link */}
      <div className="border-t border-[var(--border-default)] px-4 py-2.5">
        <button
          onClick={() => router.push("/workspaces")}
          className="flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface)]"
        >
          <ArrowLeft className="h-4 w-4 shrink-0" />
          全部 workspace
        </button>
      </div>
    </aside>
  );
}
```

**Step 2: Verify no import errors**

Run: `cd /home/cjz/wenjin/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`

**Step 3: Commit**

```bash
git add frontend/components/workspace/AppShellSidebar.tsx
git commit -m "feat: redesign sidebar with compact stepper, remove verbose sections"
```

---

### Task 5: Overhaul the dashboard page

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/page.tsx`

**Step 1: Rewrite the dashboard**

Key changes:
1. Remove 5-stage path overview card and 4 statistics cards
2. Add new-workspace auto-redirect to chat (`threads.length === 0 && artifacts.length === 0`)
3. Smart "continue" button (label changes based on thread existence)
4. Group feature cards by stage using `workspaceStages` and `getFeatureStageId`
5. Add `id` anchors to stage groups for sidebar stepper scroll-to

```typescript
"use client";

import { useEffect, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  ArrowRight,
  Compass,
  Loader2,
  MessageSquare,
  Plus,
} from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeaturesStore } from "@/stores/features";
import { useChatStore } from "@/stores/chat";
import { useDashboardStore } from "@/stores/dashboard";
import { cn } from "@/lib/utils";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import type { WorkspaceFeature, ThreadSummary } from "@/lib/api";
import { getWorkspaceFeatureRoute } from "@/lib/workspace-feature-routes";
import { useI18n } from "@/components/i18n-provider";
import { workspaceStages, getFeatureStageId } from "@/lib/workspace-feature-stages";
import { WorkspaceInspector } from "./components/WorkspaceInspector";

const RECENT_THREADS_LIMIT = 5;

const workspaceTypeLabels: Record<string, string> = {
  sci: "学术论文",
  thesis: "学位论文",
  proposal: "研究计划",
  software_copyright: "软件著作权申请",
  patent: "专利申请",
};

const workspaceTypeColors: Record<string, string> = {
  sci: "bg-[rgba(31,66,99,0.08)] text-[var(--brand-navy)] border-[rgba(31,66,99,0.14)]",
  thesis: "bg-[rgba(92,151,165,0.08)] text-[var(--brand-cyan)] border-[rgba(92,151,165,0.18)]",
  proposal: "bg-[rgba(46,111,109,0.08)] text-[var(--brand-teal)] border-[rgba(46,111,109,0.16)]",
  software_copyright: "bg-[rgba(120,135,139,0.08)] text-[var(--text-secondary)] border-[rgba(120,135,139,0.16)]",
  patent: "bg-[rgba(166,124,57,0.09)] text-[var(--brand-brass)] border-[rgba(166,124,57,0.16)]",
};

interface RunningTask {
  id: string;
  name: string;
  progress: number;
}

function formatRelativeTime(dateString: string, locale: "cn" | "en"): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (locale === "cn") {
    if (diffMins < 1) return "刚刚";
    if (diffMins < 60) return `${diffMins} 分钟前`;
    if (diffHours < 24) return `${diffHours} 小时前`;
    if (diffDays < 7) return `${diffDays} 天前`;
    return date.toLocaleDateString("zh-CN");
  }

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffHours < 24) return `${diffHours} h ago`;
  if (diffDays < 7) return `${diffDays} d ago`;
  return date.toLocaleDateString("en-US");
}

function RunningTasksSection({
  tasks,
  workspaceId,
}: {
  tasks: RunningTask[];
  workspaceId: string;
}) {
  const router = useRouter();
  if (tasks.length === 0) return null;

  return (
    <section>
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          正在推进的任务
        </h2>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        {tasks.map((task) => (
          <button
            key={task.id}
            type="button"
            onClick={() => router.push(`/workspaces/${workspaceId}/chat/new`)}
            className="route-card flex w-full items-center gap-4 rounded-2xl px-5 py-4 text-left transition-transform hover:-translate-y-0.5"
          >
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-[var(--brand-brass)]" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                {task.name}
              </p>
              <div className="mt-2 flex items-center gap-3">
                <div className="h-1.5 flex-1 rounded-full bg-[var(--bg-muted)]">
                  <div
                    className="h-full rounded-full bg-[var(--brand-brass)] transition-all"
                    style={{ width: `${Math.min(task.progress, 100)}%` }}
                  />
                </div>
                <span className="text-xs tabular-nums text-[var(--text-muted)]">
                  {task.progress}%
                </span>
              </div>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function StagedFeatureCards({
  features,
  workspaceId,
}: {
  features: WorkspaceFeature[];
  workspaceId: string;
}) {
  const router = useRouter();

  // Group features by stage
  const grouped = useMemo(() => {
    const groups = new Map<string, WorkspaceFeature[]>();
    for (const feature of features) {
      const stageId = getFeatureStageId(feature.id);
      const existing = groups.get(stageId) ?? [];
      existing.push(feature);
      groups.set(stageId, existing);
    }
    // Return in stage order, only stages that have features
    return workspaceStages
      .filter((stage) => groups.has(stage.id))
      .map((stage) => ({ stage, features: groups.get(stage.id)! }));
  }, [features]);

  if (grouped.length === 0) return null;

  return (
    <section>
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          工作模块
        </h2>
      </div>
      <div className="space-y-6">
        {grouped.map(({ stage, features: stageFeatures }) => (
          <div key={stage.id} id={`stage-${stage.id}`}>
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
              {stage.title}
            </p>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {stageFeatures.map((feature) => {
                const route = getWorkspaceFeatureRoute(workspaceId, feature.id);
                return (
                  <button
                    key={feature.id}
                    type="button"
                    onClick={() => route && router.push(route)}
                    className="route-card flex items-start gap-3 rounded-2xl p-4 text-left transition-transform hover:-translate-y-0.5"
                  >
                    <span
                      className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-xl bg-[rgba(31,66,99,0.08)] text-lg leading-none"
                      role="img"
                    >
                      {feature.icon}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-[var(--text-primary)]">
                        {feature.name}
                      </p>
                      <p className="mt-1.5 line-clamp-2 text-xs leading-5 text-[var(--text-muted)]">
                        {feature.description}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function RecentConversations({
  threads,
  workspaceId,
  locale,
}: {
  threads: ThreadSummary[];
  workspaceId: string;
  locale: "cn" | "en";
}) {
  const router = useRouter();

  if (threads.length === 0) return null;

  return (
    <section>
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          最近对话
        </h2>
      </div>
      <div className="space-y-2">
        {threads.map((thread, index) => (
          <motion.button
            type="button"
            key={thread.id}
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.04 }}
            onClick={() =>
              router.push(`/workspaces/${workspaceId}/chat/${thread.id}`)
            }
            className="flex w-full items-center gap-3 rounded-xl border border-[var(--border-default)] bg-white/76 p-3 text-left transition-colors hover:bg-[var(--bg-surface)]"
          >
            <div className="rounded-lg bg-[var(--bg-surface)] p-2">
              <MessageSquare className="h-4 w-4 text-[var(--text-muted)]" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                {thread.title || "未命名对话"}
              </p>
              <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                {formatRelativeTime(thread.updated_at, locale)}
              </p>
            </div>
          </motion.button>
        ))}
      </div>
    </section>
  );
}

export default function WorkbenchPage() {
  const params = useParams();
  const router = useRouter();
  const { locale } = useI18n();
  const workspaceId = params.id as string;

  const { workspace, isWorkspaceLoading, error, artifacts } =
    useWorkspaceStore();
  const { features } = useFeaturesStore();
  const { threads, loadThreads } = useChatStore();
  const { modules, fetchDashboard, reset: resetDashboard } =
    useDashboardStore();

  useEffect(() => {
    if (workspaceId) {
      void fetchDashboard(workspaceId);
      void loadThreads(workspaceId);
    }
    return () => {
      resetDashboard();
    };
  }, [workspaceId, fetchDashboard, loadThreads, resetDashboard]);

  const runningTasks = useMemo<RunningTask[]>(() => {
    const featureById = new Map(features.map((f) => [f.id, f]));
    return modules
      .filter((m) => m.status === "in_progress")
      .map((m) => ({
        id: m.id,
        name: featureById.get(m.id)?.name ?? m.id,
        progress:
          typeof m.summary?.progress === "number"
            ? Math.round(m.summary.progress as number)
            : 0,
      }));
  }, [modules, features]);

  const recentThreads = useMemo(
    () => threads.slice(0, RECENT_THREADS_LIMIT),
    [threads]
  );

  const recommendedFeature = useMemo(
    () => features[0] ?? null,
    [features]
  );

  // New workspace auto-redirect: no threads and no artifacts → go to chat
  useEffect(() => {
    if (
      workspace &&
      !isWorkspaceLoading &&
      threads.length === 0 &&
      artifacts.length === 0 &&
      features.length > 0
    ) {
      router.replace(
        `/workspaces/${workspaceId}/chat/new?onboarding=true`
      );
    }
  }, [
    workspace,
    isWorkspaceLoading,
    threads.length,
    artifacts.length,
    features.length,
    router,
    workspaceId,
  ]);

  if (isWorkspaceLoading || (!workspace && !error)) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--bg-base)]">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col items-center gap-4"
        >
          <Loader2 className="h-8 w-8 animate-spin text-[var(--accent-primary)]" />
          <p className="text-[var(--text-secondary)]">正在加载...</p>
        </motion.div>
      </div>
    );
  }

  if (error || !workspace) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--bg-base)]">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center"
        >
          <p className="mb-4 text-red-500">{error || "Workspace not found"}</p>
          <button
            onClick={() => router.push("/workspaces")}
            className="rounded-2xl bg-[var(--accent-primary)] px-4 py-2 text-white transition-colors hover:bg-[var(--accent-primary)]/90"
          >
            返回 workspace 列表
          </button>
        </motion.div>
      </div>
    );
  }

  // Smart button: continue last thread or start new
  const hasThreads = threads.length > 0;
  const continueLabel = hasThreads ? "继续上次对话" : "新对话";
  const continueTarget = hasThreads
    ? `/workspaces/${workspaceId}/chat/${threads[0].id}`
    : `/workspaces/${workspaceId}/chat/new`;

  return (
    <div className="flex h-screen flex-col bg-[var(--bg-base)]">
      {/* Header — slim */}
      <header className="border-b border-[var(--border-default)] bg-[rgba(251,248,242,0.92)] px-6 py-4 backdrop-blur-xl">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.96 }}
              onClick={() => router.push("/workspaces")}
              className="rounded-xl border border-[var(--border-default)] bg-white/80 p-2.5 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface)]"
            >
              <ArrowLeft className="h-4 w-4" />
            </motion.button>
            <div className="min-w-0">
              <h1 className="text-xl font-semibold text-[var(--text-primary)]">
                {workspace.name}
              </h1>
              <div className="mt-1.5 flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    "rounded-full border px-2.5 py-0.5 text-[11px] font-medium",
                    workspaceTypeColors[workspace.type] ||
                      "border-[var(--border-default)] bg-white/80 text-[var(--text-primary)]"
                  )}
                >
                  {workspaceTypeLabels[workspace.type] || workspace.type}
                </span>
                {workspace.discipline && (
                  <span className="rounded-full border border-[var(--border-default)] bg-white/80 px-2.5 py-0.5 text-[11px] text-[var(--text-secondary)]">
                    {workspace.discipline}
                  </span>
                )}
              </div>
            </div>
          </div>

          <button
            onClick={() => router.push(continueTarget)}
            className="inline-flex items-center gap-2 rounded-2xl bg-gradient-to-r from-[var(--brand-navy)] to-[var(--brand-teal)] px-5 py-2.5 text-sm font-medium text-white shadow-[0_8px_20px_rgba(31,66,99,0.16)] transition-shadow hover:shadow-[0_12px_24px_rgba(31,66,99,0.22)]"
          >
            <Compass className="h-4 w-4" />
            {continueLabel}
          </button>
        </div>
      </header>

      <ErrorBoundary>
        <main className="flex-1 overflow-auto p-6">
          <div className="mx-auto grid max-w-7xl gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
            <div className="space-y-8">
              {/* Recommended next step */}
              {recommendedFeature && (
                <section className="route-card rounded-2xl p-5">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--accent-secondary)]">
                    推荐下一步
                  </p>
                  <h3 className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
                    {recommendedFeature.name}
                  </h3>
                  <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                    {recommendedFeature.description}
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      const route = getWorkspaceFeatureRoute(
                        workspaceId,
                        recommendedFeature.id
                      );
                      if (route) router.push(route);
                    }}
                    className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-[var(--brand-navy)]"
                  >
                    开始
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </section>
              )}

              <RunningTasksSection
                tasks={runningTasks}
                workspaceId={workspaceId}
              />

              <StagedFeatureCards
                features={features}
                workspaceId={workspaceId}
              />

              <RecentConversations
                threads={recentThreads}
                workspaceId={workspaceId}
                locale={locale}
              />
            </div>

            <div className="min-h-0">
              <WorkspaceInspector workspaceId={workspaceId} />
            </div>
          </div>
        </main>
      </ErrorBoundary>
    </div>
  );
}
```

**Step 2: Verify no import errors**

Run: `cd /home/cjz/wenjin/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`

**Step 3: Commit**

```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/page.tsx
git commit -m "feat: slim dashboard — remove stage overview and stats, group features by stage, add onboarding redirect"
```

---

### Task 6: Add onboarding entry prompt support in chat

**Files:**
- Modify: `frontend/lib/workspace-chat-entry.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/chat/[threadId]/page.tsx`

**Step 1: Add onboarding prompt builder to `workspace-chat-entry.ts`**

Add this function at the end of the file:

```typescript
const onboardingPrompts: Record<string, string> = {
  thesis:
    "用户刚刚创建了一个「学位论文」工作区。请用简洁友好的口吻欢迎用户，告诉他你可以帮他完成从选题调研到终稿交付的全过程，然后问他论文题目或研究方向是什么。如果用户还没定题，引导他说说感兴趣的领域。",
  sci:
    "用户刚刚创建了一个「学术论文」工作区。请用简洁友好的口吻欢迎用户，告诉他你可以帮他完成文献调研、框架设计、论文撰写和投稿推荐等工作，然后问他论文的研究主题或方向。",
  proposal:
    "用户刚刚创建了一个「研究计划」工作区。请用简洁友好的口吻欢迎用户，告诉他你可以帮他完成课题背景调研、方案设计和计划书撰写，然后问他课题方向或已有的想法。",
  software_copyright:
    "用户刚刚创建了一个「软件著作权申请」工作区。请用简洁友好的口吻欢迎用户，告诉他你可以帮他生成软件说明书和申请材料，然后问他软件名称和主要功能。",
  patent:
    "用户刚刚创建了一个「专利申请」工作区。请用简洁友好的口吻欢迎用户，告诉他你可以帮他完成技术交底、权利要求书撰写和现有技术检索，然后问他要申请专利的技术方案是什么。",
};

export function buildOnboardingEntryPrompt(workspaceType: string): string {
  return onboardingPrompts[workspaceType] ?? onboardingPrompts.sci;
}
```

**Step 2: Update chat page to handle `onboarding=true`**

In the chat page component, read the `onboarding` search param. When it's `true` and there's no entry seed from a feature, construct an onboarding message to send as the first system-context prompt.

Read the current chat page file and add handling for the `onboarding` param. The exact integration depends on how `ChatPanel` receives and uses `entrySeed`. The key change is:

```typescript
// In the chat page, after parsing entrySeed:
const isOnboarding = searchParams.get("onboarding") === "true";

// Pass to ChatPanel as a new prop or construct a synthetic entry seed:
const effectiveEntrySeed = entrySeed ?? (isOnboarding && workspace ? {
  featureId: "__onboarding__",
  skillId: null,
  params: { __onboarding_type: workspace.type },
} : null);
```

Then in `buildWorkspaceChatEntryPrompt`, handle the `__onboarding__` featureId:

```typescript
// Add at the start of buildWorkspaceChatEntryPrompt:
if (seed.featureId === "__onboarding__") {
  const wsType = String(seed.params.__onboarding_type ?? "sci");
  return buildOnboardingEntryPrompt(wsType);
}
```

**Step 3: Commit**

```bash
git add frontend/lib/workspace-chat-entry.ts frontend/app/\(workbench\)/workspaces/\[id\]/chat/\[threadId\]/page.tsx
git commit -m "feat: add onboarding entry prompt for new workspaces"
```

---

### Task 7: Update CommandPalette to use chat routes

**Files:**
- Modify: `frontend/components/workspace/CommandPalette.tsx`

**Step 1: Change import from `getWorkspaceFeatureRoute` — no code change needed**

Since we already changed `getWorkspaceFeatureRoute` to delegate to `getWorkspaceFeatureChatRoute` in Task 2, the CommandPalette will automatically use chat routes. No changes needed here.

**Step 2: Verify by reading the file**

Confirm that `CommandPalette.tsx` line 15 imports `getWorkspaceFeatureRoute` and line 97 uses it. Since we changed that function in Task 2, this already works.

**Step 3: Commit (skip — no changes needed)**

---

### Task 8: Update workspace creation to redirect to chat

**Files:**
- Modify: `frontend/app/workspaces/page.tsx`

**Step 1: Change the redirect after workspace creation**

In `handleCreateWorkspace`, change the redirect from dashboard to chat with onboarding:

Find line:
```typescript
router.push(`/workspaces/${created.id}`);
```

Replace with:
```typescript
router.push(`/workspaces/${created.id}/chat/new?onboarding=true`);
```

**Step 2: Commit**

```bash
git add frontend/app/workspaces/page.tsx
git commit -m "feat: redirect new workspace creation to chat with onboarding"
```

---

### Task 9: TypeScript check and visual verification

**Step 1: Run TypeScript check**

Run: `cd /home/cjz/wenjin/frontend && npx tsc --noEmit --pretty 2>&1 | head -50`
Expected: No errors

**Step 2: Run build check**

Run: `cd /home/cjz/wenjin/frontend && npx next build 2>&1 | tail -30`
Expected: Build succeeds

**Step 3: Fix any issues found**

Address TypeScript or build errors if any appear.

**Step 4: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: resolve build errors from workspace UX simplification"
```
