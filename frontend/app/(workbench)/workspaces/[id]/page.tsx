"use client";

import { useEffect, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, Loader2, MessageSquare } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeaturesStore } from "@/stores/features";
import { useChatStore } from "@/stores/chat";
import { useDashboardStore } from "@/stores/dashboard";
import { RecentArtifacts } from "./components/RecentArtifacts";
import { cn } from "@/lib/utils";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import type { WorkspaceFeature, ThreadSummary } from "@/lib/api";

const RECENT_ARTIFACTS_LIMIT = 5;
const RECENT_THREADS_LIMIT = 5;

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

/* ------------------------------------------------------------------ */
/*  Running Tasks Section                                              */
/* ------------------------------------------------------------------ */

interface RunningTask {
  id: string;
  name: string;
  progress: number; // 0–100
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
      <h2 className="text-sm font-medium text-[var(--text-muted)] mb-3">
        进行中的任务
      </h2>
      <div className="space-y-2">
        {tasks.map((task) => (
          <button
            key={task.id}
            type="button"
            onClick={() =>
              router.push(`/workspaces/${workspaceId}/chat/new`)
            }
            className="flex w-full items-center gap-4 rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-3 text-left transition-colors hover:bg-[var(--bg-muted)]"
          >
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-amber-500" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                {task.name}
              </p>
              <div className="mt-1.5 flex items-center gap-2">
                <div className="h-1.5 flex-1 rounded-full bg-[var(--bg-muted)]">
                  <div
                    className="h-full rounded-full bg-amber-500 transition-all"
                    style={{ width: `${Math.min(task.progress, 100)}%` }}
                  />
                </div>
                <span className="shrink-0 text-xs tabular-nums text-[var(--text-muted)]">
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

/* ------------------------------------------------------------------ */
/*  Feature Cards Grid                                                 */
/* ------------------------------------------------------------------ */

function FeatureCardsGrid({
  features,
  workspaceId,
}: {
  features: WorkspaceFeature[];
  workspaceId: string;
}) {
  const router = useRouter();

  return (
    <section>
      <h2 className="text-sm font-medium text-[var(--text-muted)] mb-3">
        功能模块
      </h2>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {features.map((feature) => {
          const skillId = feature.id.replace(/_/g, "-");
          return (
            <button
              key={feature.id}
              type="button"
              onClick={() =>
                router.push(
                  `/workspaces/${workspaceId}/chat/new?skill=${skillId}`
                )
              }
              className="flex items-start gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 text-left transition-colors hover:bg-[var(--bg-muted)]"
            >
              <span className="mt-0.5 text-xl leading-none" role="img">
                {feature.icon}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  {feature.name}
                </p>
                <p className="mt-1 line-clamp-2 text-xs text-[var(--text-muted)]">
                  {feature.description}
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Recent Conversations                                               */
/* ------------------------------------------------------------------ */

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "刚刚";
  if (diffMins < 60) return `${diffMins} 分钟前`;
  if (diffHours < 24) return `${diffHours} 小时前`;
  if (diffDays < 7) return `${diffDays} 天前`;
  return date.toLocaleDateString("zh-CN");
}

function RecentConversations({
  threads,
  workspaceId,
}: {
  threads: ThreadSummary[];
  workspaceId: string;
}) {
  const router = useRouter();

  if (threads.length === 0) {
    return (
      <div className="text-center py-8 text-[var(--text-muted)]">
        <MessageSquare className="w-10 h-10 mx-auto mb-2 opacity-50" />
        <p className="text-sm">暂无对话</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {threads.map((thread, index) => (
        <motion.button
          type="button"
          key={thread.id}
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: index * 0.05 }}
          onClick={() =>
            router.push(`/workspaces/${workspaceId}/chat/${thread.id}`)
          }
          className="flex w-full items-center gap-3 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 text-left transition-colors hover:bg-[var(--bg-muted)]"
        >
          <div className="p-2 rounded-lg bg-[var(--bg-elevated)]">
            <MessageSquare className="w-4 h-4 text-[var(--text-muted)]" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-[var(--text-primary)] truncate">
              {thread.title || "未命名对话"}
            </p>
            <p className="text-xs text-[var(--text-muted)]">
              {formatRelativeTime(thread.updated_at)}
            </p>
          </div>
        </motion.button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Page                                                          */
/* ------------------------------------------------------------------ */

export default function WorkbenchPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;

  const { workspace, isWorkspaceLoading, error, artifacts } =
    useWorkspaceStore();
  const { features } = useFeaturesStore();
  const { threads, loadThreads } = useChatStore();
  const {
    modules,
    fetchDashboard,
    reset: resetDashboard,
  } = useDashboardStore();

  // Fetch dashboard data on mount
  useEffect(() => {
    if (workspaceId) {
      void fetchDashboard(workspaceId);
      void loadThreads(workspaceId);
    }
    return () => {
      resetDashboard();
    };
  }, [workspaceId, fetchDashboard, loadThreads, resetDashboard]);

  // Derive running tasks from modules + features
  const runningTasks = useMemo<RunningTask[]>(() => {
    const featureById = new Map(features.map((f) => [f.id, f]));
    return modules
      .filter((m) => m.status === "in_progress")
      .map((m) => {
        const feature = featureById.get(m.id);
        const progress =
          typeof m.summary?.progress === "number"
            ? Math.round(m.summary.progress as number)
            : 0;
        return {
          id: m.id,
          name: feature?.name ?? m.id,
          progress,
        };
      });
  }, [modules, features]);

  // Recent threads (first N)
  const recentThreads = useMemo(
    () => threads.slice(0, RECENT_THREADS_LIMIT),
    [threads]
  );

  // ---- Loading state ----
  if (isWorkspaceLoading || (!workspace && !error)) {
    return (
      <div className="h-screen flex items-center justify-center bg-[var(--bg-base)]">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col items-center gap-4"
        >
          <Loader2 className="w-8 h-8 text-academic-primary animate-spin" />
          <p className="text-slate-500 dark:text-slate-400">
            Loading workspace...
          </p>
        </motion.div>
      </div>
    );
  }

  // ---- Error state ----
  if (error || !workspace) {
    return (
      <div className="h-screen flex items-center justify-center bg-[var(--bg-base)]">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center"
        >
          <p className="text-red-500 mb-4">
            {error || "Workspace not found"}
          </p>
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

  // ---- Normal render ----
  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      {/* ---- Header ---- */}
      <header className="h-16 flex items-center justify-between px-6 bg-[var(--glass-bg)] backdrop-blur-xl border-b border-[var(--glass-border)]">
        <div className="flex items-center gap-4">
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => router.push("/workspaces")}
            className={cn(
              "p-2 rounded-lg",
              "bg-[var(--bg-surface)]",
              "hover:bg-[var(--bg-muted)]",
              "text-[var(--text-secondary)]",
              "transition-colors"
            )}
          >
            <ArrowLeft className="w-5 h-5" />
          </motion.button>

          <div>
            <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              {workspace.name}
            </h1>
            {workspace.description && (
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {workspace.description}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span
            className={cn(
              "px-3 py-1 rounded-full text-xs font-medium",
              workspaceTypeColors[workspace.type] ||
                "bg-slate-500/10 text-slate-600"
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
            onClick={() =>
              router.push(`/workspaces/${workspaceId}/chat/new`)
            }
            className="flex items-center gap-2 rounded-lg bg-academic-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-academic-primary/90"
          >
            <MessageSquare className="h-4 w-4" />
            Chat
          </button>
        </div>
      </header>

      {/* ---- Main content ---- */}
      <ErrorBoundary>
        <main className="flex-1 overflow-auto p-6">
          <div className="max-w-7xl mx-auto space-y-6">
            {/* Running Tasks (conditional) */}
            <RunningTasksSection
              tasks={runningTasks}
              workspaceId={workspaceId}
            />

            {/* Feature Cards */}
            <FeatureCardsGrid
              features={features}
              workspaceId={workspaceId}
            />

            {/* Bottom row: Recent Conversations + Recent Artifacts */}
            <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div>
                <h2 className="text-sm font-medium text-[var(--text-muted)] mb-3">
                  最近对话
                </h2>
                <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
                  <RecentConversations
                    threads={recentThreads}
                    workspaceId={workspaceId}
                  />
                </div>
              </div>

              <div>
                <h2 className="text-sm font-medium text-[var(--text-muted)] mb-3">
                  最近产出
                </h2>
                <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
                  <RecentArtifacts
                    artifacts={artifacts.slice(0, RECENT_ARTIFACTS_LIMIT)}
                  />
                </div>
              </div>
            </section>
          </div>
        </main>
      </ErrorBoundary>
    </div>
  );
}
