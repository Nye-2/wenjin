"use client";

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Activity,
  Bot,
  BookOpen,
  CheckCircle,
  Clock3,
  FileCode,
  FileText,
  GitBranch,
  Lightbulb,
  ListChecks,
  Loader2,
  MessageSquareText,
  SearchCheck,
  ShieldCheck,
  Sparkles,
  Target,
  XCircle,
} from "lucide-react";
import {
  useWorkspaceStore,
  type Artifact,
  type WorkspaceActivityItem,
} from "@/stores/workspace";
import { useFeaturesStore } from "@/stores/features";
import { ArtifactDetailDialog } from "@/components/workspace/ArtifactDetailDialog";
import { cn } from "@/lib/utils";

const artifactIcons: Record<string, React.ElementType> = {
  hypothesis: Lightbulb,
  literature: BookOpen,
  literature_review: BookOpen,
  framework_outline: ListChecks,
  outline: ListChecks,
  "research-gap": GitBranch,
  copyright_materials: ShieldCheck,
  technical_description: FileCode,
  patent_outline: ShieldCheck,
  prior_art_report: SearchCheck,
  background_research: BookOpen,
  paper_analysis: GitBranch,
  draft: FileText,
  paper_draft: FileText,
  code: FileCode,
  opening_report: ListChecks,
  feasibility_analysis: CheckCircle,
  thesis_chapter: FileText,
  gap_analysis: Target,
  figure: FileCode,
  research_ideas: Lightbulb,
  literature_search_results: BookOpen,
  default: FileText,
};

const artifactColors: Record<string, string> = {
  hypothesis: "text-amber-500 bg-amber-500/10",
  literature: "text-blue-500 bg-blue-500/10",
  literature_review: "text-blue-500 bg-blue-500/10",
  framework_outline: "text-purple-500 bg-purple-500/10",
  outline: "text-purple-500 bg-purple-500/10",
  "research-gap": "text-rose-500 bg-rose-500/10",
  copyright_materials: "text-violet-500 bg-violet-500/10",
  technical_description: "text-indigo-500 bg-indigo-500/10",
  patent_outline: "text-amber-500 bg-amber-500/10",
  prior_art_report: "text-orange-500 bg-orange-500/10",
  background_research: "text-emerald-500 bg-emerald-500/10",
  paper_analysis: "text-fuchsia-500 bg-fuchsia-500/10",
  draft: "text-emerald-500 bg-emerald-500/10",
  paper_draft: "text-emerald-500 bg-emerald-500/10",
  code: "text-cyan-500 bg-cyan-500/10",
  opening_report: "text-amber-500 bg-amber-500/10",
  feasibility_analysis: "text-green-500 bg-green-500/10",
  thesis_chapter: "text-purple-500 bg-purple-500/10",
  gap_analysis: "text-red-500 bg-red-500/10",
  figure: "text-cyan-500 bg-cyan-500/10",
  research_ideas: "text-amber-500 bg-amber-500/10",
  literature_search_results: "text-blue-500 bg-blue-500/10",
  default: "text-slate-500 bg-slate-500/10",
};

type ActivityFilter = "all" | WorkspaceActivityItem["kind"];

const filterOptions: Array<{ value: ActivityFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "feature_task", label: "功能" },
  { value: "chat_thread", label: "对话" },
  { value: "subagent_task", label: "子代理" },
  { value: "artifact", label: "产出" },
];

function formatTime(dateString: string) {
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
  return date.toLocaleDateString();
}

function getStatusMeta(status?: string | null) {
  switch (status) {
    case "running":
    case "pending":
    case "in_progress":
      return {
        label: status === "pending" ? "排队中" : "进行中",
        className: "bg-amber-500/10 text-amber-600",
        icon: Loader2,
      };
    case "success":
    case "completed":
      return {
        label: "已完成",
        className: "bg-emerald-500/10 text-emerald-600",
        icon: CheckCircle,
      };
    case "failed":
    case "timed_out":
      return {
        label: "失败",
        className: "bg-red-500/10 text-red-600",
        icon: XCircle,
      };
    case "cancelled":
      return {
        label: "已取消",
        className: "bg-slate-500/10 text-slate-600",
        icon: Clock3,
      };
    case "draft":
    case "review":
    case "final":
      return {
        label: status,
        className: "bg-slate-500/10 text-slate-600",
        icon: FileText,
      };
    default:
      return null;
  }
}

function getActivityMeta(item: WorkspaceActivityItem, artifact?: Artifact | null) {
  if (item.kind === "artifact") {
    const artifactType =
      typeof item.metadata?.artifact_type === "string"
        ? item.metadata.artifact_type
        : artifact?.type || "default";
    return {
      label: "产出",
      icon: artifactIcons[artifactType] || artifactIcons.default,
      className: artifactColors[artifactType] || artifactColors.default,
    };
  }

  if (item.kind === "feature_task") {
    return {
      label: "功能",
      icon: Sparkles,
      className: "text-blue-500 bg-blue-500/10",
    };
  }

  if (item.kind === "chat_thread") {
    return {
      label: "对话",
      icon: MessageSquareText,
      className: "text-emerald-500 bg-emerald-500/10",
    };
  }

  return {
    label: "子代理",
    icon: Bot,
    className: "text-violet-500 bg-violet-500/10",
  };
}

function resolveSummary(item: WorkspaceActivityItem) {
  if (item.summary) {
    return item.summary;
  }

  if (item.kind === "chat_thread") {
    const count = typeof item.metadata?.message_count === "number"
      ? item.metadata.message_count
      : null;
    return count ? `${count} 条消息` : "会话已更新";
  }

  if (item.kind === "subagent_task") {
    return typeof item.metadata?.prompt === "string" ? item.metadata.prompt : "子代理任务";
  }

  return "最近活动";
}

function resolveMetadataLine(
  item: WorkspaceActivityItem,
  featureName?: string,
) {
  if (item.kind === "feature_task") {
    return featureName || item.title;
  }

  if (item.kind === "chat_thread") {
    const skill = typeof item.metadata?.skill === "string" ? item.metadata.skill : null;
    const messageCount =
      typeof item.metadata?.message_count === "number" ? item.metadata.message_count : null;
    const detail = [skill ? skill.replace(/-/g, " ") : null, messageCount ? `${messageCount} 条消息` : null]
      .filter(Boolean)
      .join(" · ");
    return detail || "对话活动";
  }

  if (item.kind === "subagent_task") {
    return item.subagent_type ? item.subagent_type.replace(/[-_]/g, " ") : "子代理任务";
  }

  if (item.kind === "artifact") {
    const artifactType = typeof item.metadata?.artifact_type === "string"
      ? item.metadata.artifact_type
      : null;
    const skill = typeof item.metadata?.created_by_skill === "string"
      ? item.metadata.created_by_skill
      : null;
    return [artifactType?.replace(/[_-]/g, " "), skill].filter(Boolean).join(" · ") || "工作区产出";
  }

  return "活动";
}

interface ActivityItemRowProps {
  item: WorkspaceActivityItem;
  artifact: Artifact | null;
  featureName?: string;
  onSelectArtifact: (artifact: Artifact) => void;
}

function ActivityItemRow({
  item,
  artifact,
  featureName,
  onSelectArtifact,
}: ActivityItemRowProps) {
  const meta = getActivityMeta(item, artifact);
  const statusMeta = getStatusMeta(item.status);
  const Icon = meta.icon;
  const clickable = item.kind === "artifact" && artifact !== null;
  const metadataLine = resolveMetadataLine(item, featureName);

  const content = (
    <>
      <div className="relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)]">
        <div className={cn("rounded-lg p-2", meta.className)}>
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-muted)]">
                {meta.label}
              </span>
              {statusMeta && (
                <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium", statusMeta.className)}>
                  <statusMeta.icon
                    className={cn(
                      "h-3 w-3",
                      (item.status === "running" || item.status === "pending") && "animate-spin"
                    )}
                  />
                  {statusMeta.label}
                </span>
              )}
            </div>
            <p className="mt-2 truncate text-sm font-medium text-[var(--text-primary)]">
              {featureName || item.title}
            </p>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">
              {resolveSummary(item)}
            </p>
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              {metadataLine}
            </p>
          </div>
          <span className="shrink-0 text-[11px] text-[var(--text-muted)]">
            {formatTime(item.occurred_at)}
          </span>
        </div>
      </div>
    </>
  );

  if (clickable && artifact) {
    return (
      <motion.button
        type="button"
        initial={{ opacity: 0, x: -12 }}
        animate={{ opacity: 1, x: 0 }}
        onClick={() => onSelectArtifact(artifact)}
        className="group relative flex w-full items-start gap-3 rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-3 text-left transition-all hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-surface)]/80"
      >
        {content}
      </motion.button>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      className="relative flex items-start gap-3 rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-3"
    >
      {content}
    </motion.div>
  );
}

interface KnowledgePanelProps {
  workspaceId: string;
}

export function KnowledgePanel({ workspaceId }: KnowledgePanelProps) {
  void workspaceId;
  const {
    activities,
    artifacts,
    isActivityLoading,
  } = useWorkspaceStore();
  const { getFeatureById } = useFeaturesStore();
  const [filter, setFilter] = useState<ActivityFilter>("all");
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);

  const visibleItems = useMemo(() => {
    if (filter === "all") {
      return activities;
    }
    return activities.filter((item) => item.kind === filter);
  }, [activities, filter]);

  return (
    <>
      <div className="flex h-full min-w-0 flex-col rounded-3xl border border-[var(--border-default)] bg-[var(--bg-elevated)] backdrop-blur-xl">
        <div className="border-b border-[var(--border-default)] px-4 py-4">
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-[var(--accent-primary)]" />
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              Workspace Activity
            </h2>
          </div>
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            Feature、对话、子代理和产出统一时间线
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {filterOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setFilter(option.value)}
                className={cn(
                  "rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors",
                  filter === option.value
                    ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
                    : "bg-[var(--bg-surface)] text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-3">
          <AnimatePresence mode="popLayout">
            {isActivityLoading && activities.length === 0 ? (
              <div className="flex items-center justify-center py-8">
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                  className="h-6 w-6 rounded-full border-2 border-[var(--accent-primary)] border-t-transparent"
                />
              </div>
            ) : visibleItems.length === 0 ? (
              <div className="py-8 text-center">
                <Activity className="mx-auto mb-2 h-10 w-10 text-[var(--text-muted)]" />
                <p className="text-sm text-[var(--text-secondary)]">暂无活动</p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  执行功能、开始对话或生成产出后，这里会出现工作区时间线
                </p>
              </div>
            ) : (
              <div className="relative space-y-3">
                <div className="absolute left-8 top-0 bottom-0 w-px bg-gradient-to-b from-[var(--accent-primary)]/40 via-[var(--accent-secondary)]/20 to-transparent" />
                {visibleItems.map((item) => {
                  const artifact = item.artifact_id
                    ? artifacts.find((candidate) => candidate.id === item.artifact_id) ?? null
                    : null;
                  const featureName = item.feature_id
                    ? getFeatureById(item.feature_id)?.name
                    : undefined;

                  return (
                    <ActivityItemRow
                      key={item.id}
                      item={item}
                      artifact={artifact}
                      featureName={featureName}
                      onSelectArtifact={setSelectedArtifact}
                    />
                  );
                })}
              </div>
            )}
          </AnimatePresence>
        </div>
      </div>

      <ArtifactDetailDialog
        artifact={selectedArtifact}
        open={selectedArtifact !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedArtifact(null);
          }
        }}
      />
    </>
  );
}
