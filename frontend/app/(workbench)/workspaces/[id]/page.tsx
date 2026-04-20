"use client";

import { useEffect, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Code,
  Compass,
  FileText,
  FlaskConical,
  Image as ImageIcon,
  Lightbulb,
  List,
  Loader2,
  Microscope,
  Package,
  Pen,
  Search,
  ShieldCheck,
} from "lucide-react";
import { useExecutionStore } from "@/stores/execution";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeaturesStore } from "@/stores/features";
import { cn } from "@/lib/utils";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import type { ExecutionSession, WorkspaceFeature } from "@/lib/api";
import { useI18n } from "@/components/i18n-provider";
import { workspaceStages, getFeatureStageId } from "@/lib/workspace-feature-stages";
import { WorkspaceInspector } from "./components/WorkspaceInspector";

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
const EMPTY_EXECUTION_SESSIONS: ExecutionSession[] = [];

interface RunningTask {
  id: string;
  name: string;
  progress: number;
}

function StaticFeatureIcon({
  name,
  className,
}: {
  name: string | null | undefined;
  className?: string;
}) {
  switch (name) {
    case "book-open":
      return <BookOpen className={className} />;
    case "file-text":
      return <FileText className={className} />;
    case "list":
      return <List className={className} />;
    case "pen":
      return <Pen className={className} />;
    case "image":
      return <ImageIcon className={className} />;
    case "package":
      return <Package className={className} />;
    case "microscope":
      return <Microscope className={className} />;
    case "shield-check":
      return <ShieldCheck className={className} />;
    case "compass":
      return <Compass className={className} />;
    case "flask-conical":
      return <FlaskConical className={className} />;
    case "lightbulb":
      return <Lightbulb className={className} />;
    case "code":
      return <Code className={className} />;
    default:
      return <Search className={className} />;
  }
}

/* -------------------------------------------------------------------------- */
/*  Smart recommendation logic                                                */
/* -------------------------------------------------------------------------- */

function inferRecommendedFeature(
  features: WorkspaceFeature[],
  artifacts: { type: string }[],
): WorkspaceFeature | null {
  if (features.length === 0) return null;

  const artifactTypes = new Set(artifacts.map((a) => a.type));
  const hasDraft =
    artifactTypes.has("THESIS_CHAPTER") || artifactTypes.has("PAPER_DRAFT");
  const hasOutline =
    artifactTypes.has("FRAMEWORK_OUTLINE") || artifactTypes.has("ABSTRACT");
  const hasResearch =
    artifactTypes.has("DEEP_RESEARCH_REPORT") ||
    artifactTypes.has("LITERATURE_SEARCH_RESULTS") ||
    artifactTypes.has("BACKGROUND_RESEARCH");

  if (hasDraft) {
    return (
      features.find((f) =>
        ["peer_review", "journal_recommend"].includes(f.id),
      ) ?? features[0]
    );
  }
  if (hasOutline) {
    return (
      features.find((f) =>
        ["thesis_writing", "writing"].includes(f.id),
      ) ?? features[0]
    );
  }
  if (hasResearch) {
    return (
      features.find((f) =>
        ["framework_outline", "proposal_outline", "patent_outline"].includes(
          f.id,
        ),
      ) ?? features[0]
    );
  }
  return features[0];
}

/* -------------------------------------------------------------------------- */
/*  Running Tasks                                                             */
/* -------------------------------------------------------------------------- */

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
            onClick={() => router.push(`/workspaces/${workspaceId}/chat`)}
            className="route-card-hover flex w-full items-center gap-4 rounded-2xl px-5 py-4 text-left"
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

/* -------------------------------------------------------------------------- */
/*  Staged Feature Cards (with Lucide icons + staggered animation)            */
/* -------------------------------------------------------------------------- */

function StagedFeatureCards({
  features,
}: {
  features: WorkspaceFeature[];
}) {
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

  let globalIndex = 0;

  return (
    <section>
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">工作模块</h2>
      </div>
      <div className="space-y-6">
        {grouped.map(({ stage, features: stageFeatures }) => (
          <div key={stage.id} id={`stage-${stage.id}`}>
            <p className="section-accent mb-3 text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
              {stage.title}
            </p>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {stageFeatures.map((feature) => {
                const delay = globalIndex * 0.04;
                globalIndex++;
                return (
                  <motion.div
                    key={feature.id}
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay, duration: 0.35, ease: "easeOut" }}
                    className="route-card-hover flex items-start gap-3 rounded-2xl p-4 text-left"
                  >
                    <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[rgba(31,66,99,0.06)]">
                      <StaticFeatureIcon
                        name={feature.icon}
                        className="h-[18px] w-[18px] text-[var(--brand-navy)]"
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-[var(--text-primary)]">
                        {feature.name}
                      </p>
                      <p className="mt-1.5 line-clamp-2 text-xs leading-5 text-[var(--text-muted)]">
                        {feature.description}
                      </p>
                      <p className="mt-2 text-[11px] leading-5 text-[var(--text-secondary)]">
                        在对话中表达这一步目标后，问津会判断是否启用该模块。
                      </p>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/*  Page                                                                      */
/* -------------------------------------------------------------------------- */

export default function WorkbenchPage() {
  const params = useParams();
  const router = useRouter();
  useI18n();
  const workspaceId = params.id as string;

  const workspace = useWorkspaceStore((state) => state.workspace);
  const isWorkspaceLoading = useWorkspaceStore((state) => state.isWorkspaceLoading);
  const isArtifactsLoading = useWorkspaceStore((state) => state.isArtifactsLoading);
  const error = useWorkspaceStore((state) => state.error);
  const artifacts = useWorkspaceStore((state) => state.artifacts);
  const features = useFeaturesStore((state) => state.features);
  const executionSessions = useExecutionStore(
    (state) => state.byWorkspace[workspaceId] ?? EMPTY_EXECUTION_SESSIONS
  );

  // Auto-redirect new workspaces to onboarding chat (only on first load)
  useEffect(() => {
    if (
      workspace &&
      !isWorkspaceLoading &&
      !isArtifactsLoading &&
      artifacts.length === 0 &&
      features.length > 0 &&
      !sessionStorage.getItem(`wenjin-onboarded-${workspaceId}`)
    ) {
      sessionStorage.setItem(`wenjin-onboarded-${workspaceId}`, "1");
      router.replace(`/workspaces/${workspaceId}/chat?onboarding=true`);
    }
  }, [workspace, isWorkspaceLoading, isArtifactsLoading, artifacts.length, features.length, router, workspaceId]);

  const runningTasks = useMemo<RunningTask[]>(() => {
    const featureById = new Map(features.map((feature) => [feature.id, feature]));
    return executionSessions
      .filter(
        (execution) =>
          execution.status === "running" ||
          execution.status === "pending" ||
          execution.status === "awaiting_user_input"
      )
      .map((execution) => ({
        id: execution.primary_task_id || execution.id,
        name:
          featureById.get(execution.feature_id)?.name ?? execution.feature_id,
        progress:
          typeof execution.progress === "number"
            ? Math.round(execution.progress)
            : typeof execution.runtime_snapshot?.progress === "number"
              ? Math.round(execution.runtime_snapshot.progress as number)
              : 0,
      }));
  }, [executionSessions, features]);

  const recommendedFeature = useMemo(
    () => inferRecommendedFeature(features, artifacts),
    [features, artifacts],
  );

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

  const recommendedIconName = recommendedFeature?.icon ?? null;

  return (
    <div className="flex h-screen flex-col bg-[var(--bg-base)]">
      <ErrorBoundary>
        <main className="flex-1 overflow-auto p-6 atmosphere-mesh">
          <div className="mx-auto grid max-w-7xl gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(430px,520px)]">
            <div className="space-y-6">
              {/* ── Hero Section ────────────────────────────────────── */}
              <motion.section
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45, ease: "easeOut" }}
                className="route-card-featured relative overflow-hidden rounded-2xl"
              >
                <div className="relative p-6">
                  {/* Top row: back + tags + CTA */}
                  <div className="flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <motion.button
                        whileHover={{ scale: 1.04 }}
                        whileTap={{ scale: 0.96 }}
                        onClick={() => router.push("/workspaces")}
                        className="rounded-2xl border border-[var(--border-default)] bg-white/80 p-2.5 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface)]"
                      >
                        <ArrowLeft className="h-4 w-4" />
                      </motion.button>

                      <span
                        className={cn(
                          "rounded-full border px-3 py-1 text-xs font-medium",
                          workspaceTypeColors[workspace.type] ||
                            "border-[var(--border-default)] bg-white/80 text-[var(--text-primary)]",
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

                    <button
                      onClick={() =>
                        router.push(`/workspaces/${workspaceId}/chat`)
                      }
                      className="inline-flex items-center gap-2 rounded-2xl bg-gradient-to-r from-[var(--brand-navy)] to-[var(--brand-teal)] px-5 py-2.5 text-sm font-medium text-white shadow-[0_12px_24px_rgba(31,66,99,0.18)] transition-shadow hover:shadow-[0_16px_28px_rgba(31,66,99,0.22)]"
                    >
                      <Compass className="h-4 w-4" />
                      进入对话
                      <ArrowRight className="h-3.5 w-3.5 opacity-70" />
                    </button>
                  </div>

                  {/* Hero title + description */}
                  <div className="mt-6">
                    <h1 className="text-2xl font-semibold tracking-tight text-[var(--text-primary)]">
                      {workspace.name}
                    </h1>
                    {workspace.description ? (
                      <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
                        {workspace.description}
                      </p>
                    ) : null}
                  </div>

                  {/* Embedded recommendation */}
                  {recommendedFeature && recommendedIconName ? (
                    <div className="mt-6 rounded-xl border border-[var(--border-default)] bg-white/60 p-4 backdrop-blur-sm">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
                        推荐下一步
                      </p>
                      <div className="mt-3 flex items-start gap-3">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[rgba(31,66,99,0.06)]">
                          <StaticFeatureIcon
                            name={recommendedIconName}
                            className="h-[18px] w-[18px] text-[var(--brand-navy)]"
                          />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-[var(--text-primary)]">
                            {recommendedFeature.name}
                          </p>
                          <p className="mt-1 text-xs leading-5 text-[var(--text-muted)]">
                            {recommendedFeature.description}
                          </p>
                        </div>
                        <p className="text-right text-[11px] leading-5 text-[var(--text-secondary)]">
                          在对话中提出这一步，问津会先确认是否开始。
                        </p>
                      </div>
                    </div>
                  ) : null}
                </div>
              </motion.section>

              <RunningTasksSection tasks={runningTasks} workspaceId={workspaceId} />

              <StagedFeatureCards features={features} />
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
