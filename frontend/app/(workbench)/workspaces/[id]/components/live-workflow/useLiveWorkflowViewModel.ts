import { useMemo } from "react";

import type { ExecutionRecord, WorkspacePrismReviewItem } from "@/lib/api/types";
import { runViewFromExecution } from "@/lib/execution-run-view";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";
import type { WorkbenchTab } from "@/stores/workbench-layout-store";

import type { EvidenceItem } from "./types";
import { isTerminalStatus } from "./utils";

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
  previews: WorkspaceResultPreview[];
  reviewItems: WorkspacePrismReviewItem[];
  evidenceItems: EvidenceItem[];
  selectedPreview: WorkspaceResultPreview | null;
  runningRecord: ExecutionRecord | null;
  pendingReviewCount: number;
  sandboxCount: number;
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
  const activeRecord = records.find((record) => record.id === activeRunId) ?? null;
  if (activeRecord && !isTerminalStatus(activeRecord.status)) {
    return activeRecord;
  }

  const focusedRecord = records.find((record) => record.id === focusedRunId) ?? null;
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
}: {
  selectedRecord: ExecutionRecord | null;
  previews: WorkspaceResultPreview[];
  reviewItems: WorkspacePrismReviewItem[];
  evidenceItems: EvidenceItem[];
}): WorkbenchTab {
  if (!selectedRecord) {
    return "overview";
  }
  if (!isTerminalStatus(selectedRecord.status)) {
    return "run";
  }
  if (previews.length > 0 || reviewItems.length > 0) {
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
  const runView = selectedRecord ? runViewFromExecution(selectedRecord) : null;
  const previews = runView?.resultPreviews ?? [];
  const reviewItems = runView?.reviewItems ?? [];
  const evidenceItems = runView?.evidenceItems ?? [];
  const selectedPreview =
    previews.find((preview) => preview.id === input.selectedPreviewId) ??
    previews[0] ??
    null;
  const runningRecord = selectedRecord && !isTerminalStatus(selectedRecord.status)
    ? selectedRecord
    : records.find((record) => !isTerminalStatus(record.status)) ?? null;
  const pendingReviewCount = runView?.pendingReviewCount ?? 0;
  const sandboxCount = runView?.sandboxCount ?? 0;

  return {
    records,
    selectedRecord,
    previews,
    reviewItems,
    evidenceItems,
    selectedPreview,
    runningRecord,
    pendingReviewCount,
    sandboxCount,
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
