import { useMemo } from "react";

import type { ExecutionRecord, WorkspacePrismReviewItem } from "@/lib/api/types";
import {
  buildWorkspaceResultPreviewsFromOutputs,
  buildWorkspaceResultPreviewsFromReviewItems,
} from "@/lib/workspace-result-preview";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";
import {
  applyDraftEditsToOutputs,
  extractTaskOutputs,
} from "@/lib/workbench-result-editing";
import type { WorkbenchDraftEdit, WorkbenchTab } from "@/stores/workbench-layout-store";

import type { EvidenceItem } from "./types";
import {
  buildEvidenceItems,
  isTerminalStatus,
  readReviewItems,
} from "./utils";

export interface LiveWorkflowViewModelInput {
  records: ExecutionRecord[];
  workspaceId: string;
  selectedRunId: string | null;
  focusedRunId: string | null;
  activeRunId: string | null;
  selectedPreviewId: string | null;
  draftEdits: Record<string, WorkbenchDraftEdit>;
}

export interface LiveWorkflowViewModel {
  records: ExecutionRecord[];
  selectedRecord: ExecutionRecord | null;
  baseOutputs: ReturnType<typeof extractTaskOutputs>;
  editedOutputs: ReturnType<typeof extractTaskOutputs>;
  previews: WorkspaceResultPreview[];
  reviewItems: WorkspacePrismReviewItem[];
  evidenceItems: EvidenceItem[];
  outputSignature: string;
  selectedPreview: WorkspaceResultPreview | null;
  selectedDraft: WorkbenchDraftEdit | undefined;
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
  const baseOutputs = extractTaskOutputs(selectedRecord?.result);
  const editedOutputs = applyDraftEditsToOutputs(baseOutputs, input.draftEdits);
  const reviewItems = readReviewItems(selectedRecord);
  const outputPreviews = buildWorkspaceResultPreviewsFromOutputs(editedOutputs);
  const reviewPreviews = buildWorkspaceResultPreviewsFromReviewItems(reviewItems);
  const previews = [...outputPreviews, ...reviewPreviews];
  const evidenceItems = buildEvidenceItems(selectedRecord, previews);
  const outputSignature = baseOutputs
    .map((output) => `${output.id}:${output.default_checked !== false}`)
    .join("|");
  const selectedPreview =
    previews.find((preview) => preview.id === input.selectedPreviewId) ??
    previews[0] ??
    null;
  const runningRecord = selectedRecord && !isTerminalStatus(selectedRecord.status)
    ? selectedRecord
    : records.find((record) => !isTerminalStatus(record.status)) ?? null;
  const pendingReviewCount = outputPreviews.length + reviewItems.length;
  const sandboxCount = evidenceItems.filter(
    (item) => item.kind === "sandbox" || item.summary.includes("sandbox"),
  ).length;

  return {
    records,
    selectedRecord,
    baseOutputs,
    editedOutputs,
    previews,
    reviewItems,
    evidenceItems,
    outputSignature,
    selectedPreview,
    selectedDraft: selectedPreview ? input.draftEdits[selectedPreview.id] : undefined,
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
    draftEdits,
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
        draftEdits,
      }),
    [
      records,
      workspaceId,
      selectedRunId,
      focusedRunId,
      activeRunId,
      selectedPreviewId,
      draftEdits,
    ],
  );
}
