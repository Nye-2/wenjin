"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  ExternalLink,
  MessageSquareText,
  RefreshCw,
} from "lucide-react";
import type { Artifact, Workspace, WorkspaceActivityItem } from "@/stores/workspace";
import {
  readWorkspaceFeatureOrchestrationParams,
  resolveWorkspaceFeatureActionContext,
  type WorkspaceFeatureActionContext,
} from "@/lib/workspace-feature-action-context";
import { cn } from "@/lib/utils";
import {
  ActivityItemRow,
  type ActivityFilter,
  inferActivityModuleId,
  workspaceActivityFilterOptions,
} from "./WorkspaceKnowledgePanelSupport";

type FeatureRouteParams = WorkspaceFeatureActionContext["routeParams"];

interface WorkspaceActivityTimelineProps {
  workspaceId: string;
  workspace: Workspace | null | undefined;
  artifacts: Artifact[];
  activities: WorkspaceActivityItem[];
  visibleItems: WorkspaceActivityItem[];
  isActivityLoading: boolean;
  filter: ActivityFilter;
  moduleFilter: string;
  moduleOptions: Array<{ id: string; label: string }>;
  onFilterChange: (filter: ActivityFilter) => void;
  onModuleFilterChange: (moduleId: string) => void;
  resolveFeatureName: (featureId: string) => string | undefined;
  resolveFeature?: (featureId: string) => { id: string; followUpPrompt?: string | null } | undefined;
  resolveActivityTitle: (
    item: WorkspaceActivityItem,
    featureName?: string
  ) => string;
  resolveSkillLabel: (skillId: string | null | undefined) => string | null;
  onSelectArtifact: (artifact: Artifact) => void;
  onOpenDetails: (item: WorkspaceActivityItem) => void;
  onOpenThread: (threadId: string) => void;
  onOpenModule: (
    featureId: string | null | undefined,
    routeParams?: FeatureRouteParams | null
  ) => void;
  onRetryFeatureTask: (
    item: WorkspaceActivityItem,
    actionContext: WorkspaceFeatureActionContext
  ) => void;
}

export function WorkspaceActivityTimeline({
  workspaceId,
  workspace,
  artifacts,
  activities,
  visibleItems,
  isActivityLoading,
  filter,
  moduleFilter,
  moduleOptions,
  onFilterChange,
  onModuleFilterChange,
  resolveFeatureName,
  resolveFeature,
  resolveActivityTitle,
  resolveSkillLabel,
  onSelectArtifact,
  onOpenDetails,
  onOpenThread,
  onOpenModule,
  onRetryFeatureTask,
}: WorkspaceActivityTimelineProps) {
  return (
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
          {workspaceActivityFilterOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onFilterChange(option.value)}
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
            onChange={(event) => onModuleFilterChange(event.target.value)}
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
                  ? resolveFeatureName(featureId)
                  : undefined;
                const title = resolveActivityTitle(item, featureName);
                const feature = featureId && resolveFeature ? resolveFeature(featureId) : undefined;
                const actionContext = resolveWorkspaceFeatureActionContext({
                  workspaceId,
                  featureId,
                  feature: feature ?? null,
                  workspace,
                  artifacts,
                  orchestrationParams: readWorkspaceFeatureOrchestrationParams(
                    item.metadata?.params
                  ),
                });
                const route = actionContext.route;
                const actions = [];

                if (item.kind === "feature_task" && route) {
                  actions.push({
                    key: "open-module",
                    label: "打开模块",
                    icon: ExternalLink,
                    onClick: () => onOpenModule(featureId, actionContext.routeParams),
                    tone: "primary" as const,
                  });
                }
                if (
                  item.kind === "feature_task" &&
                  item.status === "failed" &&
                  featureId &&
                  actionContext.rerunParams
                ) {
                  actions.push({
                    key: "retry-task",
                    label: "重试",
                    icon: RefreshCw,
                    onClick: () => onRetryFeatureTask(item, actionContext),
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
                    onClick: () => onOpenThread(item.thread_id!),
                    tone: "primary" as const,
                  });
                }

                return (
                  <ActivityItemRow
                    key={item.id}
                    item={item}
                    artifact={artifact}
                    title={title}
                    resolveSkillLabel={resolveSkillLabel}
                    onSelectArtifact={onSelectArtifact}
                    onOpenDetails={onOpenDetails}
                    actions={actions}
                  />
                );
              })}
            </div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
