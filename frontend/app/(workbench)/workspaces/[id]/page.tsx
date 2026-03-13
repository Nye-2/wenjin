"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, Loader2 } from "lucide-react";
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

const workspaceTypeLabels: Record<string, string> = {
  sci: "Scientific Paper",
  thesis: "Thesis / Dissertation",
  proposal: "Research Proposal",
  software_copyright: "Software Copyright Application",
  patent: "Patent Application",
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
};

export default function WorkbenchPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;

  const { workspace, isWorkspaceLoading, error, loadWorkspace, clearWorkspace, artifacts, fetchArtifacts } =
    useWorkspaceStore();
  const { features, fetchFeatures, clearFeatures } = useFeaturesStore();
  const { modules, fetchDashboard, reset: resetDashboard } = useDashboardStore();

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
        <main className="flex-1 overflow-auto p-6">
          <div className="max-w-6xl mx-auto space-y-6">
            {/* Module Cards Grid */}
            <section>
              <h2 className="text-sm font-medium text-[var(--text-muted)] mb-4">
                工作模块
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {features.map((feature) => {
                  const moduleStatus = modules.find((m) => m.id === feature.id);
                  const route = featureRouteMap[feature.id] || feature.id;

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
                <RecentArtifacts artifacts={artifacts.slice(0, 5)} />
              </div>
            </section>
          </div>
        </main>
      </div>
    );
  }

  // Other workspace types use original three-column layout
  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      {/* Header */}
      <header className="h-16 flex items-center justify-between px-4 bg-[var(--glass-bg)] backdrop-blur-xl border-b border-[var(--glass-border)]">
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

      {/* Main Content - Three Columns */}
      <ErrorBoundary>
        <main className="flex-1 flex overflow-hidden">
          <LazyKnowledgePanel workspaceId={workspaceId} />
          <LazyChatPanel workspaceId={workspaceId} />
          <LazyLiteraturePanel workspaceId={workspaceId} />
        </main>
      </ErrorBoundary>
    </div>
  );
}
