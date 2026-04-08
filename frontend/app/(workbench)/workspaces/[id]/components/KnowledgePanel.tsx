"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  useWorkspaceStore,
  type Artifact,
  type WorkspaceActivityItem,
} from "@/stores/workspace";
import { useFeaturesStore } from "@/stores/features";
import { ArtifactDetailDialog } from "@/components/workspace/ArtifactDetailDialog";
import {
  type ActivityFilter,
  inferActivityModuleId,
} from "./WorkspaceKnowledgePanelSupport";
import { WorkspaceActivityDetailDialog } from "./WorkspaceActivityDetailDialog";
import { WorkspaceActivityTimeline } from "./WorkspaceActivityTimeline";

interface KnowledgePanelProps {
  workspaceId: string;
  embedded?: boolean;
}

export function KnowledgePanel({
  workspaceId,
  embedded = false,
}: KnowledgePanelProps) {
  const router = useRouter();
  const {
    activities,
    artifacts,
    isActivityLoading,
  } = useWorkspaceStore();
  const { getFeatureById, getSkillById } = useFeaturesStore();
  const [filter, setFilter] = useState<ActivityFilter>("all");
  const [moduleFilter, setModuleFilter] = useState<string>("all");
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [selectedActivity, setSelectedActivity] = useState<WorkspaceActivityItem | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const resolveSkillLabel = (skillId: string | null | undefined): string | null =>
    skillId ? (getSkillById(skillId)?.name ?? skillId) : null;

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
  const selectedActivityArtifact =
    selectedActivity?.artifact_id
      ? artifacts.find((candidate) => candidate.id === selectedActivity.artifact_id) ?? null
      : null;
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

  const openThread = async () => {
    router.push(`/workspaces/${workspaceId}/chat`);
    setSelectedActivity(null);
  };

  return (
    <>
      <WorkspaceActivityTimeline
        artifacts={artifacts}
        activities={activities}
        embedded={embedded}
        visibleItems={visibleItems}
        isActivityLoading={isActivityLoading}
        filter={filter}
        moduleFilter={moduleFilter}
        moduleOptions={moduleOptions}
        onFilterChange={setFilter}
        onModuleFilterChange={setModuleFilter}
        resolveFeatureName={(featureId) => getFeatureById(featureId)?.name}
        resolveActivityTitle={resolveActivityTitle}
        resolveSkillLabel={resolveSkillLabel}
        onSelectArtifact={setSelectedArtifact}
        onOpenDetails={setSelectedActivity}
        onOpenThread={() => void openThread()}
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
        actionError={actionError}
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
        onOpenThread={() => void openThread()}
      />
    </>
  );
}
