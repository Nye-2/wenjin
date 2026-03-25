"use client";

import { useEffect, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, Loader2, Clock3, CheckCircle2, AlertCircle } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeaturesStore } from "@/stores/features";
import { useDashboardStore } from "@/stores/dashboard";
import {
  LazyKnowledgePanel,
  LazyChatPanel,
  LazyLiteraturePanel,
} from "@/components/workspace/lazy-panels";
import { TaskSummaryStrip } from "@/components/workspace";
import { ModuleCard } from "./components/ModuleCard";
import { RecentArtifacts } from "./components/RecentArtifacts";
import { cn } from "@/lib/utils";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import {
  getWorkspaceFeatureRoute,
  workspaceFeatureRouteMap,
} from "@/lib/workspace-feature-routes";
import { isWorkspaceChatCockpitEnabled } from "@/lib/workspace-rollout";
import type { WorkspaceFeature } from "@/lib/api";

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

type ModuleStatusValue = "not_started" | "in_progress" | "completed" | "failed";

const moduleStatusOrder: ModuleStatusValue[] = [
  "not_started",
  "in_progress",
  "completed",
  "failed",
];

const moduleStatusMeta: Record<
  ModuleStatusValue,
  { label: string; badgeClass: string; iconClass: string }
> = {
  not_started: {
    label: "未开始",
    badgeClass: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
    iconClass: "text-slate-500",
  },
  in_progress: {
    label: "进行中",
    badgeClass: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
    iconClass: "text-amber-500",
  },
  completed: {
    label: "已完成",
    badgeClass: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
    iconClass: "text-emerald-500",
  },
  failed: {
    label: "失败",
    badgeClass: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
    iconClass: "text-red-500",
  },
};

const moduleStatusIconMap = {
  not_started: Clock3,
  in_progress: Loader2,
  completed: CheckCircle2,
  failed: AlertCircle,
} as const;

function normalizeModuleStatus(status: string | undefined): ModuleStatusValue {
  if (status === "in_progress") return "in_progress";
  if (status === "completed") return "completed";
  if (status === "failed") return "failed";
  return "not_started";
}

interface TaskTrackProps {
  workspaceId: string;
  features: WorkspaceFeature[];
  modules: Array<{ id: string; status: string }>;
  recommendedFeatureIds: string[];
}

function TaskTrack({
  workspaceId,
  features,
  modules,
  recommendedFeatureIds,
}: TaskTrackProps) {
  const router = useRouter();
  const recommendedSet = new Set(recommendedFeatureIds);
  const moduleById = new Map(modules.map((module) => [module.id, module.status]));

  return (
    <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-[var(--text-primary)]">任务轨道</h2>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          主线模块按任务顺序排列，推荐项会优先高亮。
        </p>
      </div>
      <div className="space-y-2">
        {features.map((feature, index) => {
          const status = normalizeModuleStatus(moduleById.get(feature.id));
          const isRecommended = recommendedSet.has(feature.id);
          const route = workspaceFeatureRouteMap[feature.id];
          return (
            <button
              type="button"
              key={feature.id}
              onClick={() =>
                router.push(route ? `/workspaces/${workspaceId}/${route}` : `/workspaces/${workspaceId}`)
              }
              className={cn(
                "flex w-full items-center gap-3 rounded-xl border px-3 py-3 text-left transition-colors",
                isRecommended
                  ? "border-[var(--accent-primary)]/30 bg-[var(--accent-primary)]/8"
                  : "border-[var(--border-default)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-muted)]"
              )}
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--bg-surface)] text-xs font-medium text-[var(--text-secondary)]">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                    {feature.name}
                  </p>
                  {isRecommended && (
                    <span className="rounded-full bg-[var(--accent-primary)]/10 px-2 py-0.5 text-[10px] font-medium text-[var(--accent-primary)]">
                      推荐
                    </span>
                  )}
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-[var(--text-muted)]">
                  {feature.description}
                </p>
              </div>
              <span
                className={cn(
                  "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium",
                  moduleStatusMeta[status].badgeClass
                )}
              >
                {moduleStatusMeta[status].label}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

export default function WorkbenchPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;

  const { workspace, isWorkspaceLoading, error, artifacts } = useWorkspaceStore();
  const { features } = useFeaturesStore();
  const { modules, summary, fetchDashboard, reset: resetDashboard } = useDashboardStore();

  const moduleStatusCounts = useMemo(() => {
    const counts: Record<ModuleStatusValue, number> = {
      not_started: 0,
      in_progress: 0,
      completed: 0,
      failed: 0,
    };
    const moduleStatusById = new Map(
      modules.map((module) => [module.id, module.status])
    );

    for (const feature of features) {
      const status = normalizeModuleStatus(moduleStatusById.get(feature.id));
      counts[status] += 1;
    }

    return counts;
  }, [features, modules]);

  useEffect(() => {
    if (workspaceId) {
      void fetchDashboard(workspaceId);
    }

    return () => {
      resetDashboard();
    };
  }, [workspaceId, fetchDashboard, resetDashboard]);

  const recommendedFeatureIds =
    summary?.recommended_actions.map((action) => action.feature_id) ?? [];
  const chatCockpitEnabled = isWorkspaceChatCockpitEnabled(workspace);

  if (isWorkspaceLoading || (!workspace && !error)) {
    return (
      <div className="h-screen flex items-center justify-center bg-[var(--bg-base)]">
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
      <div className="h-screen flex items-center justify-center bg-[var(--bg-base)]">
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

  const moduleStatusOverview = (
    <section>
      <h2 className="text-sm font-medium text-[var(--text-muted)] mb-4">
        模块状态概览
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {moduleStatusOrder.map((status) => {
          const meta = moduleStatusMeta[status];
          const Icon = moduleStatusIconMap[status];
          const count = moduleStatusCounts[status];
          return (
            <div
              key={status}
              className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-3"
            >
              <div className="flex items-center justify-between">
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium",
                    meta.badgeClass
                  )}
                >
                  <Icon
                    className={cn(
                      "h-3.5 w-3.5",
                      meta.iconClass,
                      status === "in_progress" && count > 0 && "animate-spin"
                    )}
                  />
                  {meta.label}
                </span>
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {count}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
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
        </div>
      </header>

      <ErrorBoundary>
        <main className="flex-1 overflow-auto p-6">
          <div className="max-w-7xl mx-auto space-y-6">
            <TaskSummaryStrip summary={summary} />

            <section className="grid grid-cols-1 gap-4 xl:grid-cols-[280px_minmax(0,1.35fr)_320px]">
              <TaskTrack
                workspaceId={workspaceId}
                features={features}
                modules={modules}
                recommendedFeatureIds={recommendedFeatureIds}
              />
              {chatCockpitEnabled ? (
                <div className="min-h-[720px] overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)]">
                  <LazyChatPanel workspaceId={workspaceId} />
                </div>
              ) : (
                <section className="min-h-[720px] rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-5">
                  <div className="max-w-2xl">
                    <h2 className="text-base font-semibold text-[var(--text-primary)]">
                      Classic Workspace Mode
                    </h2>
                    <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                      当前工作区暂未灰度开启 chat cockpit。你仍然可以从左侧任务轨道或下方工作模块进入各功能，
                      后端依然使用统一的 feature / task / artifact 执行链。
                    </p>
                  </div>

                  {summary?.current_phase && (
                    <div className="mt-6 rounded-2xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-4">
                      <p className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">
                        当前阶段
                      </p>
                      <h3 className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
                        {summary.current_phase.title}
                      </h3>
                      <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                        {summary.current_phase.description}
                      </p>
                    </div>
                  )}

                  {summary?.recommended_actions && summary.recommended_actions.length > 0 && (
                    <div className="mt-6">
                      <p className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">
                        推荐进入
                      </p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {summary.recommended_actions.map((action) => (
                          <button
                            key={action.feature_id}
                            type="button"
                            onClick={() => {
                              const route = getWorkspaceFeatureRoute(workspaceId, action.feature_id);
                              if (route) {
                                router.push(route);
                              }
                            }}
                            className="rounded-full border border-[var(--border-default)] bg-[var(--bg-muted)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)]"
                          >
                            {action.title}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </section>
              )}
              <div className="min-h-[720px] overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)]">
                <LazyLiteraturePanel workspaceId={workspaceId} />
              </div>
            </section>

            <section className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.2fr)_340px]">
              <div className="space-y-6">
                {moduleStatusOverview}

                <section>
                  <h2 className="text-sm font-medium text-[var(--text-muted)] mb-4">
                    工作模块
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {features.map((feature) => {
                      const moduleStatus = modules.find((m) => m.id === feature.id);
                      const route = workspaceFeatureRouteMap[feature.id] ?? "";

                      return (
                        <ModuleCard
                          key={feature.id}
                          workspaceId={workspaceId}
                          feature={feature}
                          moduleStatus={moduleStatus}
                          route={route}
                        />
                      );
                    })}
                  </div>
                </section>
              </div>

              <div className="space-y-4">
                <section>
                  <h2 className="text-sm font-medium text-[var(--text-muted)] mb-4">
                    最近产出
                  </h2>
                  <div className="bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-xl p-4">
                    <RecentArtifacts
                      artifacts={artifacts.slice(0, RECENT_ARTIFACTS_LIMIT)}
                    />
                  </div>
                </section>
                <div className="min-h-[420px] overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)]">
                  <LazyKnowledgePanel workspaceId={workspaceId} />
                </div>
              </div>
            </section>
          </div>
        </main>
      </ErrorBoundary>
    </div>
  );
}
