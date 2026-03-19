"use client";

import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
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
  RefreshCw,
  SearchCheck,
  ShieldCheck,
  Sparkles,
  Target,
  ExternalLink,
  XCircle,
} from "lucide-react";
import {
  useWorkspaceStore,
  type Artifact,
  type WorkspaceActivityItem,
} from "@/stores/workspace";
import { executeWorkspaceFeature } from "@/lib/api";
import { useFeaturesStore } from "@/stores/features";
import { useChatStore } from "@/stores/chat";
import { useTaskStore } from "@/stores/task";
import { ArtifactDetailDialog } from "@/components/workspace/ArtifactDetailDialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getWorkspaceFeatureRoute } from "@/lib/workspace-feature-routes";
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

function inferActivityModuleId(item: WorkspaceActivityItem): string | null {
  if (item.feature_id) {
    return item.feature_id;
  }

  const createdBySkill =
    typeof item.metadata?.created_by_skill === "string"
      ? item.metadata.created_by_skill
      : null;
  if (!createdBySkill) {
    return null;
  }

  const tail = createdBySkill.includes(".")
    ? createdBySkill.split(".").at(-1) || createdBySkill
    : createdBySkill;
  return tail.replace(/-/g, "_");
}

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

function formatLabel(key: string): string {
  return key.replace(/[_-]/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatPrimitive(value: string | number | boolean | null): string {
  if (value === null) {
    return "null";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return String(value);
}

function renderStructuredValue(value: unknown, depth: number = 0): ReactNode {
  if (value === null || value === undefined) {
    return <p className="text-sm text-[var(--text-muted)]">暂无内容</p>;
  }

  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return (
      <p className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--text-secondary)]">
        {formatPrimitive(value)}
      </p>
    );
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <p className="text-sm text-[var(--text-muted)]">暂无内容</p>;
    }

    const primitiveArray = value.every(
      (item) =>
        item === null ||
        ["string", "number", "boolean"].includes(typeof item)
    );
    if (primitiveArray) {
      return (
        <div className="flex flex-wrap gap-2">
          {value.map((item, index) => (
            <span
              key={`${formatPrimitive(item as string | number | boolean | null)}-${index}`}
              className="rounded-full bg-[var(--bg-elevated)] px-2.5 py-1 text-xs text-[var(--text-secondary)]"
            >
              {formatPrimitive(item as string | number | boolean | null)}
            </span>
          ))}
        </div>
      );
    }

    return (
      <div className="space-y-3">
        {value.map((item, index) => (
          <div
            key={index}
            className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3"
          >
            <p className="mb-2 text-xs font-medium text-[var(--text-primary)]">
              Item {index + 1}
            </p>
            {renderStructuredValue(item, depth + 1)}
          </div>
        ))}
      </div>
    );
  }

  if (typeof value === "object") {
    if (depth >= 3) {
      return (
        <pre className="overflow-x-auto rounded-lg bg-[var(--bg-elevated)] p-3 text-xs leading-6 text-[var(--text-secondary)]">
          {JSON.stringify(value, null, 2)}
        </pre>
      );
    }

    const entries = Object.entries(value as Record<string, unknown>).filter(
      ([, entryValue]) => entryValue !== undefined
    );
    if (entries.length === 0) {
      return <p className="text-sm text-[var(--text-muted)]">暂无内容</p>;
    }

    return (
      <div className="space-y-3">
        {entries.map(([key, entryValue]) => (
          <div
            key={key}
            className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3"
          >
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--text-primary)]">
              {formatLabel(key)}
            </p>
            {renderStructuredValue(entryValue, depth + 1)}
          </div>
        ))}
      </div>
    );
  }

  return (
    <pre className="overflow-x-auto rounded-lg bg-[var(--bg-elevated)] p-3 text-xs leading-6 text-[var(--text-secondary)]">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">
        {title}
      </p>
      <div className="mt-2">{children}</div>
    </div>
  );
}

function DetailFieldGrid({
  fields,
}: {
  fields: Array<[label: string, value: ReactNode]>;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {fields.map(([label, value]) => (
        <div key={label} className="rounded-lg bg-[var(--bg-elevated)] px-3 py-2">
          <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
            {label}
          </p>
          <div className="mt-1 text-sm text-[var(--text-primary)]">{value}</div>
        </div>
      ))}
    </div>
  );
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
  onOpenDetails: (item: WorkspaceActivityItem) => void;
  actions?: Array<{
    key: string;
    label: string;
    icon: React.ElementType;
    onClick: () => void;
    tone?: "default" | "primary" | "danger";
  }>;
}

function ActivityItemRow({
  item,
  artifact,
  featureName,
  onSelectArtifact,
  onOpenDetails,
  actions = [],
}: ActivityItemRowProps) {
  const meta = getActivityMeta(item, artifact);
  const statusMeta = getStatusMeta(item.status);
  const Icon = meta.icon;
  const clickableArtifact = item.kind === "artifact" && artifact !== null;
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
            {actions.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {actions.map((action) => {
                  const ActionIcon = action.icon;
                  return (
                    <button
                      key={action.key}
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        action.onClick();
                      }}
                      className={cn(
                        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors",
                        action.tone === "primary"
                          ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/15"
                          : action.tone === "danger"
                            ? "bg-red-500/10 text-red-600 hover:bg-red-500/15"
                            : "bg-[var(--bg-elevated)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                      )}
                    >
                      <ActionIcon className="h-3 w-3" />
                      {action.label}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          <span className="shrink-0 text-[11px] text-[var(--text-muted)]">
            {formatTime(item.occurred_at)}
          </span>
        </div>
      </div>
    </>
  );

  if (clickableArtifact && artifact) {
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
    <motion.button
      type="button"
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      onClick={() => onOpenDetails(item)}
      className="relative flex w-full items-start gap-3 rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-3 text-left transition-all hover:border-[var(--accent-primary)]/20"
    >
      {content}
    </motion.button>
  );
}

interface KnowledgePanelProps {
  workspaceId: string;
}

export function KnowledgePanel({ workspaceId }: KnowledgePanelProps) {
  const router = useRouter();
  const {
    activities,
    artifacts,
    isActivityLoading,
  } = useWorkspaceStore();
  const { getFeatureById } = useFeaturesStore();
  const { loadThread } = useChatStore();
  const { startTask } = useTaskStore();
  const [filter, setFilter] = useState<ActivityFilter>("all");
  const [moduleFilter, setModuleFilter] = useState<string>("all");
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [selectedActivity, setSelectedActivity] = useState<WorkspaceActivityItem | null>(null);
  const [isRetrying, setIsRetrying] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const moduleOptions = useMemo(() => {
    const seen = new Set<string>();
    const options = [];

    for (const item of activities) {
      const moduleId = inferActivityModuleId(item);
      if (!moduleId || seen.has(moduleId)) {
        continue;
      }
      seen.add(moduleId);
      options.push({
        id: moduleId,
        label: getFeatureById(moduleId)?.name || moduleId.replace(/[_-]/g, " "),
      });
    }

    return options.sort((left, right) => left.label.localeCompare(right.label, "zh-CN"));
  }, [activities, getFeatureById]);

  const visibleItems = useMemo(() => {
    return activities.filter((item) => {
      const matchesKind = filter === "all" ? true : item.kind === filter;
      const matchesModule =
        moduleFilter === "all"
          ? true
          : inferActivityModuleId(item) === moduleFilter;
      return matchesKind && matchesModule;
    });
  }, [activities, filter, moduleFilter]);

  const selectedActivityFeatureId = selectedActivity
    ? inferActivityModuleId(selectedActivity)
    : null;
  const selectedActivityFeature = selectedActivityFeatureId
    ? getFeatureById(selectedActivityFeatureId)
    : undefined;
  const selectedActivityRoute = getWorkspaceFeatureRoute(
    workspaceId,
    selectedActivityFeatureId
  );
  const selectedActivityMeta =
    selectedActivity?.metadata && typeof selectedActivity.metadata === "object"
      ? (selectedActivity.metadata as Record<string, unknown>)
      : {};
  const selectedActivityArtifact =
    selectedActivity?.artifact_id
      ? artifacts.find((candidate) => candidate.id === selectedActivity.artifact_id) ?? null
      : null;

  const openThread = async (threadId: string) => {
    await loadThread(threadId);
    setSelectedActivity(null);
  };

  const openModule = (featureId: string | null | undefined) => {
    const route = getWorkspaceFeatureRoute(workspaceId, featureId);
    if (route) {
      router.push(route);
      setSelectedActivity(null);
    }
  };

  const retryFeatureTask = async (item: WorkspaceActivityItem) => {
    const featureId = inferActivityModuleId(item);
    const feature = featureId ? getFeatureById(featureId) : undefined;
    const params =
      item.metadata?.params && typeof item.metadata.params === "object"
        ? (item.metadata.params as Record<string, unknown>)
        : {};

    if (!featureId || !feature) {
      setActionError("当前活动无法直接重试，请进入对应模块重新执行。");
      return;
    }

    setActionError(null);
    setIsRetrying(true);
    try {
      const execution = await executeWorkspaceFeature(
        workspaceId,
        featureId,
        params,
        item.thread_id || undefined
      );

      if (execution.status === "warning" && !execution.task_id) {
        setActionError(execution.message || "该功能当前无法重试");
        return;
      }

      if (!execution.task_id) {
        setActionError("任务创建失败，请稍后重试");
        return;
      }

      startTask({
        taskId: execution.task_id,
        featureId: feature.id,
        agent: feature.agent,
        agentLabel: feature.agentLabel,
        stages: feature.stages,
        initialThinking: execution.message,
      });
      setSelectedActivity(null);
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "重试失败，请稍后重试"
      );
    } finally {
      setIsRetrying(false);
    }
  };

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
          <div className="mt-3">
            <label className="mb-1 block text-[11px] font-medium text-[var(--text-muted)]">
              模块筛选
            </label>
            <select
              value={moduleFilter}
              onChange={(event) => setModuleFilter(event.target.value)}
              className="w-full rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-xs text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:outline-none"
            >
              <option value="all">全部模块</option>
              {moduleOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
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
                  const featureId = inferActivityModuleId(item);
                  const featureName = featureId
                    ? getFeatureById(featureId)?.name
                    : undefined;
                  const route = getWorkspaceFeatureRoute(workspaceId, featureId);
                  const actions = [];

                  if (item.kind === "feature_task" && route) {
                    actions.push({
                      key: "open-module",
                      label: "打开模块",
                      icon: ExternalLink,
                      onClick: () => openModule(featureId),
                      tone: "primary" as const,
                    });
                  }
                  if (
                    item.kind === "feature_task" &&
                    item.status === "failed" &&
                    featureId
                  ) {
                    actions.push({
                      key: "retry-task",
                      label: "重试",
                      icon: RefreshCw,
                      onClick: () => void retryFeatureTask(item),
                      tone: "danger" as const,
                    });
                  }
                  if (
                    (item.kind === "chat_thread" || item.kind === "subagent_task") &&
                    item.thread_id
                  ) {
                    actions.push({
                      key: "open-thread",
                      label: "打开对话",
                      icon: MessageSquareText,
                      onClick: () => void openThread(item.thread_id!),
                      tone: "primary" as const,
                    });
                  }

                  return (
                    <ActivityItemRow
                      key={item.id}
                      item={item}
                      artifact={artifact}
                      featureName={featureName}
                      onSelectArtifact={setSelectedArtifact}
                      onOpenDetails={setSelectedActivity}
                      actions={actions}
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

      <Dialog
        open={selectedActivity !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedActivity(null);
            setActionError(null);
          }
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {selectedActivityFeature?.name || selectedActivity?.title || "活动详情"}
            </DialogTitle>
            <DialogDescription>
              {selectedActivity
                ? `${selectedActivity.kind} · ${new Date(selectedActivity.occurred_at).toLocaleString("zh-CN")}`
                : "查看工作区活动详情"}
            </DialogDescription>
          </DialogHeader>

          {selectedActivity && (
            <div className="space-y-4">
              <DetailSection title="概览">
                <DetailFieldGrid
                  fields={[
                    ["活动类型", getActivityMeta(selectedActivity, selectedActivityArtifact).label],
                    ["状态", getStatusMeta(selectedActivity.status)?.label || "无"],
                    ["发生时间", new Date(selectedActivity.occurred_at).toLocaleString("zh-CN")],
                    ["关联模块", selectedActivityFeature?.name || "未关联模块"],
                    ["Thread ID", selectedActivity.thread_id || "无"],
                    ["Task ID", selectedActivity.task_id || "无"],
                  ]}
                />
              </DetailSection>

              <DetailSection title="摘要">
                <p className="text-sm leading-6 text-[var(--text-primary)]">
                  {resolveSummary(selectedActivity)}
                </p>
                <p className="mt-2 text-xs text-[var(--text-muted)]">
                  {resolveMetadataLine(
                    selectedActivity,
                    selectedActivityFeature?.name
                  )}
                </p>
              </DetailSection>

              {actionError && (
                <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600">
                  {actionError}
                </div>
              )}

              {selectedActivity.kind === "feature_task" && (
                <>
                  <DetailSection title="执行状态">
                    <DetailFieldGrid
                      fields={[
                        [
                          "进度",
                          `${typeof selectedActivityMeta.progress === "number" ? selectedActivityMeta.progress : 0}%`,
                        ],
                        [
                          "当前步骤",
                          typeof selectedActivityMeta.current_step === "string"
                            ? selectedActivityMeta.current_step
                            : "未提供",
                        ],
                        [
                          "反馈消息",
                          typeof selectedActivityMeta.message === "string"
                            ? selectedActivityMeta.message
                            : selectedActivity.status === "failed"
                              ? "执行失败"
                              : "无",
                        ],
                        [
                          "开始时间",
                          typeof selectedActivityMeta.started_at === "string"
                            ? new Date(selectedActivityMeta.started_at).toLocaleString("zh-CN")
                            : "未开始",
                        ],
                        [
                          "结束时间",
                          typeof selectedActivityMeta.completed_at === "string"
                            ? new Date(selectedActivityMeta.completed_at).toLocaleString("zh-CN")
                            : "未结束",
                        ],
                        [
                          "动作",
                          typeof selectedActivityMeta.action === "string"
                            ? selectedActivityMeta.action
                            : "默认动作",
                        ],
                      ]}
                    />
                  </DetailSection>

                  {selectedActivityMeta.params &&
                    typeof selectedActivityMeta.params === "object" && (
                      <DetailSection title="输入参数">
                        {renderStructuredValue(selectedActivityMeta.params)}
                      </DetailSection>
                    )}

                  {selectedActivityMeta.result && (
                    <DetailSection title="执行结果">
                      {renderStructuredValue(selectedActivityMeta.result)}
                    </DetailSection>
                  )}

                  {typeof selectedActivityMeta.error === "string" &&
                    selectedActivityMeta.error && (
                      <DetailSection title="错误信息">
                        <p className="text-sm leading-6 text-red-600">
                          {selectedActivityMeta.error}
                        </p>
                      </DetailSection>
                    )}
                </>
              )}

              {selectedActivity.kind === "chat_thread" && (
                <DetailSection title="会话上下文">
                  <DetailFieldGrid
                    fields={[
                      [
                        "能力",
                        typeof selectedActivityMeta.skill === "string"
                          ? selectedActivityMeta.skill.replace(/-/g, " ")
                          : "未设置",
                      ],
                      [
                        "消息数",
                        typeof selectedActivityMeta.message_count === "number"
                          ? selectedActivityMeta.message_count
                          : "未知",
                      ],
                      [
                        "最后一条角色",
                        typeof selectedActivityMeta.last_message_role === "string"
                          ? selectedActivityMeta.last_message_role
                          : "未知",
                      ],
                    ]}
                  />
                </DetailSection>
              )}

              {selectedActivity.kind === "subagent_task" && (
                <>
                  <DetailSection title="子代理上下文">
                    <DetailFieldGrid
                      fields={[
                        [
                          "代理类型",
                          selectedActivity.subagent_type
                            ? selectedActivity.subagent_type.replace(/[-_]/g, " ")
                            : "未指定",
                        ],
                        ["Thread ID", selectedActivity.thread_id || "无"],
                        ["状态", getStatusMeta(selectedActivity.status)?.label || "无"],
                      ]}
                    />
                  </DetailSection>

                  {typeof selectedActivityMeta.prompt === "string" && (
                    <DetailSection title="任务 Prompt">
                      <p className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--text-primary)]">
                        {selectedActivityMeta.prompt}
                      </p>
                    </DetailSection>
                  )}

                  {typeof selectedActivityMeta.output_preview === "string" &&
                    selectedActivityMeta.output_preview && (
                      <DetailSection title="输出摘要">
                        <p className="text-sm leading-6 text-[var(--text-primary)]">
                          {selectedActivityMeta.output_preview}
                        </p>
                      </DetailSection>
                    )}

                  {typeof selectedActivityMeta.error === "string" &&
                    selectedActivityMeta.error && (
                      <DetailSection title="错误信息">
                        <p className="text-sm leading-6 text-red-600">
                          {selectedActivityMeta.error}
                        </p>
                      </DetailSection>
                    )}
                </>
              )}

              {selectedActivity.kind === "artifact" && (
                <>
                  <DetailSection title="产出信息">
                    <DetailFieldGrid
                      fields={[
                        [
                          "产出类型",
                          typeof selectedActivityMeta.artifact_type === "string"
                            ? selectedActivityMeta.artifact_type.replace(/[_-]/g, " ")
                            : "未知",
                        ],
                        [
                          "版本",
                          typeof selectedActivityMeta.version === "number"
                            ? selectedActivityMeta.version
                            : "未知",
                        ],
                        [
                          "创建技能",
                          typeof selectedActivityMeta.created_by_skill === "string"
                            ? selectedActivityMeta.created_by_skill
                            : "未知",
                        ],
                      ]}
                    />
                  </DetailSection>

                  {selectedActivityArtifact && (
                    <DetailSection title="内容预览">
                      {renderStructuredValue(selectedActivityArtifact.content)}
                    </DetailSection>
                  )}
                </>
              )}
            </div>
          )}

          <DialogFooter>
            {selectedActivity?.kind === "artifact" && selectedActivityArtifact && (
              <button
                type="button"
                onClick={() => {
                  setSelectedArtifact(selectedActivityArtifact);
                  setSelectedActivity(null);
                }}
                className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-default)] px-3 py-2 text-sm text-[var(--text-secondary)]"
              >
                <FileText className="h-4 w-4" />
                查看完整产出
              </button>
            )}
            {selectedActivity?.thread_id && (
              <button
                type="button"
                onClick={() => void openThread(selectedActivity.thread_id!)}
                className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-default)] px-3 py-2 text-sm text-[var(--text-secondary)]"
              >
                <MessageSquareText className="h-4 w-4" />
                打开对话
              </button>
            )}
            {selectedActivityRoute && (
              <button
                type="button"
                onClick={() => openModule(selectedActivityFeatureId)}
                className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-default)] px-3 py-2 text-sm text-[var(--text-secondary)]"
              >
                <ExternalLink className="h-4 w-4" />
                打开模块
              </button>
            )}
            {selectedActivity?.kind === "feature_task" &&
              selectedActivity.status === "failed" &&
              selectedActivityFeatureId && (
                <button
                  type="button"
                  onClick={() => void retryFeatureTask(selectedActivity)}
                  disabled={isRetrying}
                  className="inline-flex items-center gap-2 rounded-lg bg-[var(--accent-primary)] px-3 py-2 text-sm text-white disabled:opacity-60"
                >
                  <RefreshCw className={cn("h-4 w-4", isRetrying && "animate-spin")} />
                  立即重试
                </button>
              )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
