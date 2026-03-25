"use client";

import { ExternalLink, FileText, MessageSquareText, RefreshCw } from "lucide-react";
import type { Artifact, WorkspaceActivityItem } from "@/stores/workspace";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { type WorkspaceFeatureActionContext } from "@/lib/workspace-feature-action-context";
import { cn } from "@/lib/utils";
import { WorkspaceActivityDetailSections } from "./WorkspaceActivityDetailSections";

type FeatureRouteParams = WorkspaceFeatureActionContext["routeParams"];

interface WorkspaceActivityDetailDialogProps {
  selectedActivity: WorkspaceActivityItem | null;
  selectedActivityFeatureId: string | null;
  selectedActivityFeatureName?: string;
  selectedActivityTitle: string;
  selectedActivityMeta: Record<string, unknown>;
  selectedActivityArtifact: Artifact | null;
  selectedActivityRoute: string | null;
  selectedActivityActionContext: WorkspaceFeatureActionContext;
  actionError: string | null;
  isRetrying: boolean;
  resolveSkillLabel: (skillId: string | null | undefined) => string | null;
  onOpenChange: (open: boolean) => void;
  onShowArtifact: (artifact: Artifact) => void;
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

export function WorkspaceActivityDetailDialog({
  selectedActivity,
  selectedActivityFeatureId,
  selectedActivityFeatureName,
  selectedActivityTitle,
  selectedActivityMeta,
  selectedActivityArtifact,
  selectedActivityRoute,
  selectedActivityActionContext,
  actionError,
  isRetrying,
  resolveSkillLabel,
  onOpenChange,
  onShowArtifact,
  onOpenThread,
  onOpenModule,
  onRetryFeatureTask,
}: WorkspaceActivityDetailDialogProps) {
  return (
    <Dialog open={selectedActivity !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{selectedActivityTitle}</DialogTitle>
          <DialogDescription>
            {selectedActivity
              ? `${selectedActivity.kind} · ${new Date(selectedActivity.occurred_at).toLocaleString("zh-CN")}`
              : "查看工作区活动详情"}
          </DialogDescription>
        </DialogHeader>

        {selectedActivity && (
          <WorkspaceActivityDetailSections
            selectedActivity={selectedActivity}
            selectedActivityFeatureName={selectedActivityFeatureName}
            selectedActivityMeta={selectedActivityMeta}
            selectedActivityArtifact={selectedActivityArtifact}
            actionError={actionError}
            resolveSkillLabel={resolveSkillLabel}
          />
        )}

        <DialogFooter>
          {selectedActivity?.kind === "artifact" && selectedActivityArtifact && (
            <button
              type="button"
              onClick={() => onShowArtifact(selectedActivityArtifact)}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-default)] px-3 py-2 text-sm text-[var(--text-secondary)]"
            >
              <FileText className="h-4 w-4" />
              查看完整产出
            </button>
          )}
          {selectedActivity?.thread_id && (
            <button
              type="button"
              onClick={() => onOpenThread(selectedActivity.thread_id!)}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-default)] px-3 py-2 text-sm text-[var(--text-secondary)]"
            >
              <MessageSquareText className="h-4 w-4" />
              打开对话
            </button>
          )}
          {selectedActivityRoute && (
            <button
              type="button"
              onClick={() =>
                onOpenModule(
                  selectedActivityFeatureId,
                  selectedActivityActionContext.routeParams
                )
              }
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-default)] px-3 py-2 text-sm text-[var(--text-secondary)]"
            >
              <ExternalLink className="h-4 w-4" />
              打开模块
            </button>
          )}
          {selectedActivity?.kind === "feature_task" &&
            selectedActivity.status === "failed" &&
            selectedActivityFeatureId &&
            selectedActivityActionContext.rerunParams && (
              <button
                type="button"
                onClick={() =>
                  onRetryFeatureTask(
                    selectedActivity,
                    selectedActivityActionContext
                  )
                }
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
  );
}
