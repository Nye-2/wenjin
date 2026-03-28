"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  useWorkspaceStore,
  type Artifact,
  type WorkspaceActivityItem,
} from "@/stores/workspace";
import { useFeaturesStore } from "@/stores/features";
import { useChatStore } from "@/stores/chat";
import { useTaskStore } from "@/stores/task";
import { ArtifactDetailDialog } from "@/components/workspace/ArtifactDetailDialog";
import {
  createWorkspaceFeatureTask,
  trackWorkspaceFeatureTask,
} from "@/lib/workspace-feature-execution";
import { getWorkspaceFeatureRoute } from "@/lib/workspace-feature-routes";
import {
  readWorkspaceFeatureOrchestrationParams,
  resolveWorkspaceFeatureActionContext,
  type WorkspaceFeatureActionContext,
} from "@/lib/workspace-feature-action-context";
import { formatWorkspaceChatSkillLabel } from "@/lib/workspace-chat-skills";
import {
  type ActivityFilter,
  inferActivityModuleId,
} from "./WorkspaceKnowledgePanelSupport";
import { WorkspaceActivityDetailDialog } from "./WorkspaceActivityDetailDialog";
import { WorkspaceActivityTimeline } from "./WorkspaceActivityTimeline";

type FeatureRouteParams = WorkspaceFeatureActionContext["routeParams"];

interface KnowledgePanelProps {
  workspaceId: string;
}

export function KnowledgePanel({ workspaceId }: KnowledgePanelProps) {
  const router = useRouter();
  const {
    workspace,
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
  const resolveSkillLabel = (skillId: string | null | undefined): string | null =>
    formatWorkspaceChatSkillLabel(workspace?.type, skillId);

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
  const selectedActivityMeta = useMemo(
    () =>
      selectedActivity?.metadata && typeof selectedActivity.metadata === "object"
        ? (selectedActivity.metadata as Record<string, unknown>)
        : {},
    [selectedActivity]
  );
  const selectedActivityActionContext = useMemo(() => {
    return resolveWorkspaceFeatureActionContext({
      workspaceId,
      featureId: selectedActivityFeatureId,
      feature: selectedActivityFeature ?? null,
      workspace,
      artifacts,
      orchestrationParams: readWorkspaceFeatureOrchestrationParams(
        selectedActivityMeta.params
      ),
    });
  }, [workspaceId, selectedActivityFeatureId, selectedActivityFeature, workspace, artifacts, selectedActivityMeta]);
  const selectedActivityArtifact =
    selectedActivity?.artifact_id
      ? artifacts.find((candidate) => candidate.id === selectedActivity.artifact_id) ?? null
      : null;
  const selectedActivityRoute = selectedActivityActionContext.route;
  const selectedSubagentTitle =
    selectedActivity && selectedActivity.kind === "subagent_task"
      ? selectedActivity.title || "未指定"
      : null;

  const resolveActivityTitle = (
    item: WorkspaceActivityItem,
    featureName?: string
  ): string => {
    if (item.kind === "subagent_task") {
      return item.title || "子代理任务";
    }
    return featureName || item.title || "活动详情";
  };

  const openThread = async (threadId: string) => {
    await loadThread(threadId);
    setSelectedActivity(null);
  };

  const openModule = (
    featureId: string | null | undefined,
    routeParams?: FeatureRouteParams | null
  ) => {
    const route = getWorkspaceFeatureRoute(
      workspaceId,
      featureId,
      routeParams ?? undefined
    );
    if (route) {
      router.push(route);
      setSelectedActivity(null);
    }
  };

  const retryFeatureTask = async (
    item: WorkspaceActivityItem,
    actionState: WorkspaceFeatureActionContext | null
  ) => {
    const featureId = inferActivityModuleId(item);
    const feature = featureId ? getFeatureById(featureId) : undefined;

    if (!featureId || !feature) {
      setActionError("当前活动无法直接重试，请进入对应模块重新执行。");
      return;
    }
    if (!actionState?.rerunParams) {
      setActionError(
        actionState?.rerunUnavailableReason || "当前活动缺少可复用的重试上下文。"
      );
      return;
    }

    setActionError(null);
    setIsRetrying(true);
    try {
      const created = await createWorkspaceFeatureTask({
        workspaceId,
        featureId: feature.id,
        params: actionState.rerunParams,
        threadId: item.thread_id || undefined,
        warningFallback: "该功能当前无法重试",
        missingTaskFallback: "任务创建失败，请稍后重试",
      });
      trackWorkspaceFeatureTask({
        feature,
        startTask,
        taskId: created.taskId,
        initialThinking: created.message,
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
      <WorkspaceActivityTimeline
        workspaceId={workspaceId}
        workspace={workspace}
        artifacts={artifacts}
        activities={activities}
        visibleItems={visibleItems}
        isActivityLoading={isActivityLoading}
        filter={filter}
        moduleFilter={moduleFilter}
        moduleOptions={moduleOptions}
        onFilterChange={setFilter}
        onModuleFilterChange={setModuleFilter}
        resolveFeatureName={(featureId) => getFeatureById(featureId)?.name}
        resolveFeature={(featureId) => getFeatureById(featureId)}
        resolveActivityTitle={resolveActivityTitle}
        resolveSkillLabel={resolveSkillLabel}
        onSelectArtifact={setSelectedArtifact}
        onOpenDetails={setSelectedActivity}
        onOpenThread={(threadId) => void openThread(threadId)}
        onOpenModule={openModule}
        onRetryFeatureTask={(item, actionContext) =>
          void retryFeatureTask(item, actionContext)
        }
      />

      <ArtifactDetailDialog
        artifact={selectedArtifact}
        open={selectedArtifact !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedArtifact(null);
          }
        }}
      />

      <WorkspaceActivityDetailDialog
        selectedActivity={selectedActivity}
        selectedActivityFeatureId={selectedActivityFeatureId}
        selectedActivityFeatureName={selectedActivityFeature?.name}
        selectedActivityTitle={
          selectedActivity?.kind === "subagent_task"
            ? selectedSubagentTitle || "未指定"
            : selectedActivityFeature?.name ||
              selectedActivity?.title ||
              "活动详情"
        }
        selectedActivityMeta={selectedActivityMeta}
        selectedActivityArtifact={selectedActivityArtifact}
        selectedActivityRoute={selectedActivityRoute}
        selectedActivityActionContext={selectedActivityActionContext}
        actionError={actionError}
        isRetrying={isRetrying}
        resolveSkillLabel={resolveSkillLabel}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedActivity(null);
            setActionError(null);
          }
        }}
        onShowArtifact={(artifact) => {
          setSelectedArtifact(artifact);
          setSelectedActivity(null);
        }}
        onOpenThread={(threadId) => void openThread(threadId)}
        onOpenModule={openModule}
        onRetryFeatureTask={(item, actionContext) =>
          void retryFeatureTask(item, actionContext)
        }
      />
    </>
  );
}
