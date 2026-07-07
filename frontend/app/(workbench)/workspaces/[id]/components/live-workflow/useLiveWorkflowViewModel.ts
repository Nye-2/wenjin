import { useMemo } from "react";

import type { ExecutionRecord, WorkspacePrismReviewItem } from "@/lib/api/types";
import type { RunViewChangeSet } from "@/lib/change-set-view";
import type { RunView, RunViewMissionState } from "@/lib/execution-run-view";
import { runViewFromExecution } from "@/lib/execution-run-view";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";
import type { WorkbenchTab } from "@/stores/workbench-layout-store";

import type { EvidenceItem } from "./types";
import { isTerminalStatus } from "./utils";

function hasPendingReview(record: ExecutionRecord | null): boolean {
  if (!record) {
    return false;
  }
  return runViewFromExecution(record).pendingReviewCount > 0;
}

export interface LiveWorkflowViewModelInput {
  records: ExecutionRecord[];
  workspaceId: string;
  selectedRunId: string | null;
  focusedRunId: string | null;
  activeRunId: string | null;
  selectedPreviewId: string | null;
}

export interface LiveWorkflowViewModel {
  records: ExecutionRecord[];
  selectedRecord: ExecutionRecord | null;
  selectedRunView: RunView | null;
  mission: RunViewMissionState | null;
  previews: WorkspaceResultPreview[];
  reviewItems: WorkspacePrismReviewItem[];
  evidenceItems: EvidenceItem[];
  selectedPreview: WorkspaceResultPreview | null;
  runningRecord: ExecutionRecord | null;
  changeSet: RunViewChangeSet | null;
  pendingReviewCount: number;
  sandboxCount: number;
  hasMissionActivity: boolean;
}

export function selectLiveWorkflowRecords({
  records,
  workspaceId,
  activeRunId,
}: {
  records: ExecutionRecord[];
  workspaceId: string;
  activeRunId: string | null;
}): ExecutionRecord[] {
  return records
    .filter((record) => {
      if (record.workspace_id && record.workspace_id !== workspaceId) {
        return false;
      }
      return record.workspace_id === workspaceId || record.id === activeRunId;
    })
    .sort((left, right) => {
      const leftActive = !isTerminalStatus(left.status);
      const rightActive = !isTerminalStatus(right.status);
      if (leftActive !== rightActive) {
        return leftActive ? -1 : 1;
      }
      return (right.created_at || "").localeCompare(left.created_at || "");
    });
}

export function resolveSelectedLiveWorkflowRecord({
  records,
  selectedRunId,
  focusedRunId,
  activeRunId,
}: {
  records: ExecutionRecord[];
  selectedRunId: string | null;
  focusedRunId: string | null;
  activeRunId: string | null;
}): ExecutionRecord | null {
  const focusedRecord = records.find((record) => record.id === focusedRunId) ?? null;
  if (hasPendingReview(focusedRecord)) {
    return focusedRecord;
  }

  const activeRecord = records.find((record) => record.id === activeRunId) ?? null;
  if (activeRecord && !isTerminalStatus(activeRecord.status)) {
    return activeRecord;
  }

  if (focusedRecord && !isTerminalStatus(focusedRecord.status)) {
    return focusedRecord;
  }

  const runningRecord = records.find((record) => !isTerminalStatus(record.status));
  if (runningRecord) {
    return runningRecord;
  }

  return (
    activeRecord ??
    focusedRecord ??
    records.find((record) => record.id === selectedRunId) ??
    records[0] ??
    null
  );
}

export function resolveAutoWorkbenchTab({
  selectedRecord,
  previews,
  reviewItems,
  evidenceItems,
  pendingReviewCount = 0,
}: {
  selectedRecord: ExecutionRecord | null;
  previews: WorkspaceResultPreview[];
  reviewItems: WorkspacePrismReviewItem[];
  evidenceItems: EvidenceItem[];
  pendingReviewCount?: number;
}): WorkbenchTab {
  if (!selectedRecord) {
    return "overview";
  }
  if (!isTerminalStatus(selectedRecord.status)) {
    return "run";
  }
  if (pendingReviewCount > 0 || previews.length > 0 || reviewItems.length > 0) {
    return "review";
  }
  if (evidenceItems.length > 0) {
    return "evidence";
  }
  return "overview";
}

export function buildLiveWorkflowViewModel(
  input: LiveWorkflowViewModelInput,
): LiveWorkflowViewModel {
  const records = selectLiveWorkflowRecords({
    records: input.records,
    workspaceId: input.workspaceId,
    activeRunId: input.activeRunId,
  });
  const selectedRecord = resolveSelectedLiveWorkflowRecord({
    records,
    selectedRunId: input.selectedRunId,
    focusedRunId: input.focusedRunId,
    activeRunId: input.activeRunId,
  });
  const selectedRunView = selectedRecord ? runViewFromExecution(selectedRecord) : null;
  const previews = selectedRunView?.resultPreviews ?? [];
  const reviewItems = selectedRunView?.reviewItems ?? [];
  const evidenceItems = selectedRunView?.evidenceItems ?? [];
  const changeSet = selectedRunView?.changeSet ?? null;
  const selectedPreview =
    previews.find((preview) => preview.id === input.selectedPreviewId) ??
    previews[0] ??
    null;
  const runningRecord = selectedRecord && !isTerminalStatus(selectedRecord.status)
    ? selectedRecord
    : records.find((record) => !isTerminalStatus(record.status)) ?? null;
  const pendingReviewCount = selectedRunView?.pendingReviewCount ?? 0;
  const sandboxCount = selectedRunView?.sandboxCount ?? 0;
  const mission = selectedRunView?.mission ?? null;
  const hasMissionActivity =
    Boolean(selectedRecord) ||
    Boolean(runningRecord) ||
    pendingReviewCount > 0 ||
    evidenceItems.length > 0 ||
    Boolean(mission);

  return {
    records,
    selectedRecord,
    selectedRunView,
    mission,
    previews,
    reviewItems,
    evidenceItems,
    selectedPreview,
    runningRecord,
    changeSet,
    pendingReviewCount,
    sandboxCount,
    hasMissionActivity,
  };
}

export function useLiveWorkflowViewModel(
  input: LiveWorkflowViewModelInput,
): LiveWorkflowViewModel {
  const {
    records,
    workspaceId,
    selectedRunId,
    focusedRunId,
    activeRunId,
    selectedPreviewId,
  } = input;
  return useMemo(
    () =>
      buildLiveWorkflowViewModel({
        records,
        workspaceId,
        selectedRunId,
        focusedRunId,
        activeRunId,
        selectedPreviewId,
      }),
    [
      records,
      workspaceId,
      selectedRunId,
      focusedRunId,
      activeRunId,
      selectedPreviewId,
    ],
  );
}
