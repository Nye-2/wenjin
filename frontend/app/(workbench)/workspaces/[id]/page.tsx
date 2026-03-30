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
      <div className="grid gap-4 lg:grid-cols-2">
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

  const grouped = useMemo(() => {
    const groups = new Map<string, WorkspaceFeature[]>();
    for (const feature of features) {
      const stageId = getFeatureStageId(feature.id);
      const existing = groups.get(stageId) ?? [];
      existing.push(feature);
      groups.set(stageId, existing);
    }
    return workspaceStages
      .filter((stage) => groups.has(stage.id))
      .map((stage) => ({ stage, features: groups.get(stage.id)! }));
  }, [features]);

  if (grouped.length === 0) return null;

  return (
    <section>
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">工作模块</h2>
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
      <div className="route-card rounded-2xl p-4">
        <div className="space-y-2">
          {threads.map((thread, index) => (
            <motion.button
              type="button"
              key={thread.id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.05 }}
              onClick={() => router.push(`/workspaces/${workspaceId}/chat/${thread.id}`)}
              className="flex w-full items-center gap-3 rounded-2xl border border-[var(--border-default)] bg-white/76 p-3 text-left transition-colors hover:bg-[var(--bg-surface)]"
            >
              <div className="rounded-xl bg-[var(--bg-surface)] p-2">
                <MessageSquare className="h-4 w-4 text-[var(--text-muted)]" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                  {thread.title || "未命名分支"}
                </p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  {formatRelativeTime(thread.updated_at, locale)}
                </p>
              </div>
            </motion.button>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function WorkbenchPage() {
  const params = useParams();
  const router = useRouter();
  const { locale } = useI18n();
  const workspaceId = params.id as string;

  const { workspace, isWorkspaceLoading, error, artifacts } = useWorkspaceStore();
  const { features } = useFeaturesStore();
  const { threads, loadThreads, isThreadsLoading } = useChatStore();
  const { modules, fetchDashboard, reset: resetDashboard } = useDashboardStore();

  useEffect(() => {
    if (workspaceId) {
      void fetchDashboard(workspaceId);
      void loadThreads(workspaceId);
    }
    return () => {
      resetDashboard();
    };
  }, [workspaceId, fetchDashboard, loadThreads, resetDashboard]);

  // Auto-redirect new workspaces to onboarding chat
  useEffect(() => {
    if (workspace && !isWorkspaceLoading && !isThreadsLoading && threads.length === 0 && artifacts.length === 0 && features.length > 0) {
      router.replace(`/workspaces/${workspaceId}/chat/new?onboarding=true`);
    }
  }, [workspace, isWorkspaceLoading, isThreadsLoading, threads.length, artifacts.length, features.length, router, workspaceId]);

  const runningTasks = useMemo<RunningTask[]>(() => {
    const featureById = new Map(features.map((feature) => [feature.id, feature]));
    return modules
      .filter((module) => module.status === "in_progress")
      .map((module) => ({
        id: module.id,
        name: featureById.get(module.id)?.name ?? module.id,
        progress:
          typeof module.summary?.progress === "number"
            ? Math.round(module.summary.progress as number)
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

  const hasThreads = threads.length > 0;
  const continueLabel = hasThreads ? "继续上次对话" : "新对话";
  const continueTarget = hasThreads
    ? `/workspaces/${workspaceId}/chat/${threads[0].id}`
    : `/workspaces/${workspaceId}/chat/new`;

  if (isWorkspaceLoading || (!workspace && !error)) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--bg-base)]">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col items-center gap-4"
        >
          <Loader2 className="h-8 w-8 animate-spin text-[var(--accent-primary)]" />
          <p className="text-[var(--text-secondary)]">正在加载 workspace...</p>
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

  return (
    <div className="flex h-screen flex-col bg-[var(--bg-base)]">
      <header className="border-b border-[var(--border-default)] bg-[rgba(251,248,242,0.92)] px-6 py-5 backdrop-blur-xl">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.96 }}
              onClick={() => router.push("/workspaces")}
              className="rounded-2xl border border-[var(--border-default)] bg-white/80 p-3 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface)]"
            >
              <ArrowLeft className="h-5 w-5" />
            </motion.button>

            <div className="flex items-center gap-3">
              <h1 className="text-xl font-semibold text-[var(--text-primary)]">
                {workspace.name}
              </h1>
              <span
                className={cn(
                  "rounded-full border px-3 py-1 text-xs font-medium",
                  workspaceTypeColors[workspace.type] ||
                    "border-[var(--border-default)] bg-white/80 text-[var(--text-primary)]"
                )}
              >
                {workspaceTypeLabels[workspace.type] || workspace.type}
              </span>
              {workspace.discipline ? (
                <span className="rounded-full border border-[var(--border-default)] bg-white/80 px-3 py-1 text-xs text-[var(--text-secondary)]">
                  {workspace.discipline}
                </span>
              ) : null}
            </div>
          </div>

          <button
            onClick={() => router.push(continueTarget)}
            className="inline-flex items-center gap-2 rounded-2xl bg-gradient-to-r from-[var(--brand-navy)] to-[var(--brand-teal)] px-5 py-3 text-sm font-medium text-white shadow-[0_12px_24px_rgba(31,66,99,0.18)] transition-shadow hover:shadow-[0_16px_28px_rgba(31,66,99,0.22)]"
          >
            <Compass className="h-4 w-4" />
            {continueLabel}
          </button>
        </div>
      </header>

      <ErrorBoundary>
        <main className="flex-1 overflow-auto p-6">
          <div className="mx-auto grid max-w-7xl gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
            <div className="space-y-6">
              {recommendedFeature ? (
                <section className="route-card rounded-2xl p-6">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
                    推荐下一步
                  </p>
                  <div className="mt-4">
                    <h3 className="text-lg font-semibold text-[var(--text-primary)]">
                      {recommendedFeature.name}
                    </h3>
                    <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                      {recommendedFeature.description}
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        const route = getWorkspaceFeatureRoute(
                          workspaceId,
                          recommendedFeature.id
                        );
                        if (route) {
                          router.push(route);
                        }
                      }}
                      className="mt-5 inline-flex items-center gap-2 text-sm font-medium text-[var(--brand-navy)]"
                    >
                      打开该模块
                      <ArrowRight className="h-4 w-4" />
                    </button>
                  </div>
                </section>
              ) : null}

              <RunningTasksSection tasks={runningTasks} workspaceId={workspaceId} />

              <StagedFeatureCards features={features} workspaceId={workspaceId} />

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
