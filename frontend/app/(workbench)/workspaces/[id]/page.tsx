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
import { ModuleCard } from "./components/ModuleCard";
import { RecentArtifacts } from "./components/RecentArtifacts";
import { cn } from "@/lib/utils";
import { ErrorBoundary } from "@/components/ui/error-boundary";

// Constants
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

// Module feature to route mapping
const featureRouteMap: Record<string, string> = {
  deep_research: "deep-research",
  literature_management: "literature",
  opening_research: "opening-research",
  thesis_writing: "thesis-writing",
  figure_generation: "figure-generation",
  compile_export: "compile-export",
  literature_search: "literature-search",
  paper_analysis: "paper-analysis",
  writing: "writing",
  proposal_outline: "proposal-outline",
  background_research: "background-research",
  copyright_materials: "copyright-materials",
  technical_description: "technical-description",
  patent_outline: "patent-outline",
  prior_art_search: "prior-art-search",
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

export default function WorkbenchPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;

  const { workspace, isWorkspaceLoading, error, loadWorkspace, clearWorkspace, artifacts, fetchArtifacts } =
    useWorkspaceStore();
  const { features, fetchFeatures, clearFeatures } = useFeaturesStore();
  const { modules, fetchDashboard, reset: resetDashboard } = useDashboardStore();

  const moduleStatusCounts = useMemo(() => {
    const counts: Record<ModuleStatusValue, number> = {
      not_started: 0,
      in_progress: 0,
      completed: 0,
      failed: 0,
    };
    const moduleStatusById = new Map(modules.map((module) => [module.id, module.status]));

    for (const feature of features) {
      const status = normalizeModuleStatus(moduleStatusById.get(feature.id));
      counts[status] += 1;
    }

    return counts;
  }, [features, modules]);

  useEffect(() => {
    if (workspaceId) {
      loadWorkspace(workspaceId);
      fetchFeatures(workspaceId);
      fetchDashboard(workspaceId);
      fetchArtifacts(workspaceId);
    }

    return () => {
      clearWorkspace();
      clearFeatures();
      resetDashboard();
    };
  }, [workspaceId, loadWorkspace, clearWorkspace, fetchFeatures, clearFeatures, fetchDashboard, resetDashboard, fetchArtifacts]);

  if (isWorkspaceLoading) {
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

  // Thesis workspace uses card dashboard layout
  if (workspace.type === "thesis") {
    return (
      <div className="h-screen flex flex-col bg-[var(--bg-base)]">
        {/* Header */}
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
            {/* Type Badge */}
            <span
              className={cn(
                "px-3 py-1 rounded-full text-xs font-medium",
                workspaceTypeColors[workspace.type] || "bg-slate-500/10 text-slate-600"
              )}
            >
              {workspaceTypeLabels[workspace.type] || workspace.type}
            </span>

            {/* Discipline Badge */}
            {workspace.discipline && (
              <span className="px-3 py-1 rounded-full text-xs font-medium bg-[var(--bg-surface)] text-[var(--text-secondary)] border border-[var(--border-default)]">
                {workspace.discipline}
              </span>
            )}
          </div>
        </header>

        {/* Main Content - Card Dashboard */}
        <ErrorBoundary>
          <main className="flex-1 overflow-auto p-6">
            <div className="max-w-6xl mx-auto space-y-6">
              {moduleStatusOverview}

              {/* Module Cards Grid */}
              <section>
                <h2 className="text-sm font-medium text-[var(--text-muted)] mb-4">
                  工作模块
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {features.map((feature) => {
                    const moduleStatus = modules.find((m) => m.id === feature.id);
                    const route = featureRouteMap[feature.id] ?? "";

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

              {/* Recent Artifacts */}
              <section>
                <h2 className="text-sm font-medium text-[var(--text-muted)] mb-4">
                  最近产出
                </h2>
                <div className="bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-xl p-4">
                  <RecentArtifacts artifacts={artifacts.slice(0, RECENT_ARTIFACTS_LIMIT)} />
                </div>
              </section>
            </div>
          </main>
        </ErrorBoundary>
      </div>
    );
  }

  // Other workspace types use card dashboard layout + embedded panels
  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      {/* Header */}
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
          {/* Type Badge */}
          <span
            className={cn(
              "px-3 py-1 rounded-full text-xs font-medium",
              workspaceTypeColors[workspace.type] || "bg-slate-500/10 text-slate-600"
            )}
          >
            {workspaceTypeLabels[workspace.type] || workspace.type}
          </span>

          {/* Discipline Badge */}
          {workspace.discipline && (
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-[var(--bg-surface)] text-[var(--text-secondary)] border border-[var(--border-default)]">
              {workspace.discipline}
            </span>
          )}
        </div>
      </header>

      {/* Main Content - Card Dashboard + Panels */}
      <ErrorBoundary>
        <main className="flex-1 overflow-auto p-6">
          <div className="max-w-6xl mx-auto space-y-6">
            {moduleStatusOverview}

            {/* Module Cards Grid */}
            <section>
              <h2 className="text-sm font-medium text-[var(--text-muted)] mb-4">
                工作模块
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {features.map((feature) => {
                  const moduleStatus = modules.find((m) => m.id === feature.id);
                  const route = featureRouteMap[feature.id] ?? "";

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

            {/* Recent Artifacts */}
            <section>
              <h2 className="text-sm font-medium text-[var(--text-muted)] mb-4">
                最近产出
              </h2>
              <div className="bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-xl p-4">
                <RecentArtifacts artifacts={artifacts.slice(0, RECENT_ARTIFACTS_LIMIT)} />
              </div>
            </section>

            {/* Embedded Knowledge / Chat / Literature Panels */}
            <section className="grid grid-cols-1 lg:grid-cols-[280px_minmax(0,1.5fr)_minmax(0,1fr)] gap-4">
              <div className="min-h-[360px]">
                <LazyKnowledgePanel workspaceId={workspaceId} />
              </div>
              <div className="min-h-[360px]">
                <LazyChatPanel workspaceId={workspaceId} />
              </div>
              <div className="min-h-[360px]">
                <LazyLiteraturePanel workspaceId={workspaceId} />
              </div>
            </section>
          </div>
        </main>
      </ErrorBoundary>
    </div>
  );
}
