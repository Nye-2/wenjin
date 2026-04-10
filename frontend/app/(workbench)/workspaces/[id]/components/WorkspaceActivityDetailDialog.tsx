"use client";

import { FileText, MessageSquareText } from "lucide-react";
import type { Artifact, WorkspaceActivityItem } from "@/stores/workspace";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { WorkspaceActivityDetailSections } from "./WorkspaceActivityDetailSections";

interface WorkspaceActivityDetailDialogProps {
  selectedActivity: WorkspaceActivityItem | null;
  selectedActivityFeatureName?: string;
  selectedActivityTitle: string;
  selectedActivityMeta: Record<string, unknown>;
  selectedActivityArtifact: Artifact | null;
  selectedActivityFollowUpPrompt?: string | null;
  actionError: string | null;
  resolveSkillLabel: (skillId: string | null | undefined) => string | null;
  onOpenChange: (open: boolean) => void;
  onShowArtifact: (artifact: Artifact) => void;
  onRetryFeatureTask: () => void;
  onOpenThread: (threadId: string) => void;
}

export function WorkspaceActivityDetailDialog({
  selectedActivity,
  selectedActivityFeatureName,
  selectedActivityTitle,
  selectedActivityMeta,
  selectedActivityArtifact,
  selectedActivityFollowUpPrompt,
  actionError,
  resolveSkillLabel,
  onOpenChange,
  onShowArtifact,
  onRetryFeatureTask,
  onOpenThread,
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
            selectedActivityFollowUpPrompt={selectedActivityFollowUpPrompt}
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
          {selectedActivity?.thread_id &&
            selectedActivity.kind !== "feature_task" && (
            <button
              type="button"
              onClick={() => onOpenThread(selectedActivity.thread_id!)}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-default)] px-3 py-2 text-sm text-[var(--text-secondary)]"
            >
              <MessageSquareText className="h-4 w-4" />
              打开对话
            </button>
          )}
          {selectedActivity?.kind === "feature_task" && (
            <button
              type="button"
              onClick={onRetryFeatureTask}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-default)] px-3 py-2 text-sm text-[var(--text-secondary)]"
            >
              <MessageSquareText className="h-4 w-4" />
              重新发起
            </button>
          )}
          {selectedActivity?.kind === "feature_task" &&
            selectedActivity.thread_id && (
              <button
                type="button"
                onClick={() => onOpenThread(selectedActivity.thread_id!)}
                className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-default)] px-3 py-2 text-sm text-[var(--text-secondary)]"
              >
                <MessageSquareText className="h-4 w-4" />
                回到对话继续推进
              </button>
            )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
