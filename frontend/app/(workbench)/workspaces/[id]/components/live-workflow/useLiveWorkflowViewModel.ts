import { useMemo } from "react";

import type { ExecutionRecord, WorkspacePrismReviewItem } from "@/lib/api/types";
import { runViewFromExecution } from "@/lib/execution-run-view";
import { buildWorkspaceResultPreviewsFromOutputs } from "@/lib/workspace-result-preview";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";
import {
  applyDraftEditsToOutputs,
  extractTaskOutputs,
} from "@/lib/workbench-result-editing";
import type { WorkbenchDraftEdit, WorkbenchTab } from "@/stores/workbench-layout-store";

import type { EvidenceItem } from "./types";
import { isTerminalStatus } from "./utils";

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

function mergeEditedOutputPreviews(
  canonicalPreviews: WorkspaceResultPreview[],
  editedOutputPreviews: WorkspaceResultPreview[],
  draftEdits: Record<string, WorkbenchDraftEdit>,
): WorkspaceResultPreview[] {
  const editedIds = new Set(Object.keys(draftEdits));
  if (editedIds.size === 0) {
    return canonicalPreviews;
  }
  const editedById = new Map(
    editedOutputPreviews.map((preview) => [preview.id, preview]),
  );
  return canonicalPreviews.map((preview) => {
    if (preview.source !== "staged_output" || !editedIds.has(preview.id)) {
      return preview;
    }
    return editedById.get(preview.id) ?? preview;
  });
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
  const baseOutputs = extractTaskOutputs(selectedRecord?.result);
  const editedOutputs = applyDraftEditsToOutputs(baseOutputs, input.draftEdits);
  const editedOutputPreviews = buildWorkspaceResultPreviewsFromOutputs(editedOutputs);
  const previews = mergeEditedOutputPreviews(
    runView?.resultPreviews ?? [],
    editedOutputPreviews,
    input.draftEdits,
  );
  const reviewItems = runView?.reviewItems ?? [];
  const evidenceItems = runView?.evidenceItems ?? [];
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
  const pendingReviewCount = runView?.pendingReviewCount ?? 0;
  const sandboxCount = runView?.sandboxCount ?? 0;

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
