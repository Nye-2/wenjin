"use client";

import { useEffect, useMemo, useRef, useState, type RefObject } from "react";

import type { ExecutionRecord } from "@/lib/api/types";
import {
  acceptedUnitIdsFromChangeSet,
  commitPreviewsForChangeSetReview,
  type RunViewChangeSet,
} from "@/lib/change-set-view";
import {
  buildCommittedRoomLinks,
  COMMIT_STATE_SYNC_ERROR,
  commitExecutionOutputs,
  commitStateFromCommitResponse,
  commitStateRoomTargets,
  type ExecutionCommitRequest,
  type ExecutionCommitState,
  isExecutionCommitted,
  isExecutionDiscarded,
  isExecutionReverted,
  readCommitStateFromResult,
  resolveExecutionCommitState,
  undoExecutionCommit,
} from "@/lib/execution-commit";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";
import { useExecutionStore } from "@/stores/execution-store";

import type { RunWritebackStatus } from "./RunView";
import { generateUUID } from "./utils";

interface UseExecutionWritebackArgs {
  workspaceId: string;
  selectedRecord: ExecutionRecord | null;
  previews: WorkspaceResultPreview[];
  reviewablePreviews: WorkspaceResultPreview[];
  changeSet: RunViewChangeSet | null;
}

export function useExecutionWriteback({
  workspaceId,
  selectedRecord,
  previews,
  reviewablePreviews,
  changeSet,
}: UseExecutionWritebackArgs): RunWritebackStatus | undefined {
  const upsertExecution = useExecutionStore((state) => state.upsertExecution);
  const selectedRecordIdRef = useRef<string | null>(null);
  selectedRecordIdRef.current = selectedRecord?.id ?? null;
  const [commitState, setCommitState] = useState<{
    executionId: string | null;
    idempotencyKey: string;
    committing: boolean;
    reverting: boolean;
    responseCommitState: ExecutionCommitState | null;
    linkPreviews: WorkspaceResultPreview[] | null;
    error: string | null;
  }>(() => emptyCommitState(selectedRecord?.id ?? null));

  const durableCommitState = readCommitStateFromResult(selectedRecord?.result);
  const localCommitState =
    commitState.executionId === selectedRecord?.id
      ? commitState.responseCommitState
      : null;
  const effectiveCommitState = resolveExecutionCommitState({
    localCommitState,
    durableCommitState,
  });
  const commitFinal = Boolean(effectiveCommitState);
  const commitLinkPreviews =
    commitState.executionId === selectedRecord?.id && commitState.linkPreviews
      ? commitState.linkPreviews
      : previews;
  const commitLinks = useMemo(
    () =>
      buildCommittedRoomLinks({
        workspaceId,
        previews: commitLinkPreviews,
        roomTargets: commitStateRoomTargets(effectiveCommitState),
      }),
    [commitLinkPreviews, effectiveCommitState, workspaceId],
  );
  const acceptedCommitPreviews = useMemo(
    () =>
      commitPreviewsForChangeSetReview({
        changeSet,
        previews,
        visiblePreviews: reviewablePreviews,
      }),
    [changeSet, previews, reviewablePreviews],
  );
  const acceptedUnitIds = useMemo(
    () => acceptedUnitIdsFromChangeSet(changeSet),
    [changeSet],
  );
  const saveCount = changeSet
    ? acceptedUnitIds.length
    : acceptedCommitPreviews.length;

  useEffect(() => {
    setCommitState(emptyCommitState(selectedRecord?.id ?? null));
  }, [selectedRecord?.id]);

  async function handleCommit() {
    if (!selectedRecord || commitState.committing || commitState.reverting || commitFinal) {
      return;
    }
    if (selectedRecord.status !== "completed" || saveCount === 0) {
      return;
    }
    const requestExecutionId = selectedRecord.id;
    const requestIdempotencyKey = commitState.idempotencyKey;
    const requestPreviews = acceptedCommitPreviews;
    const body: ExecutionCommitRequest =
      changeSet && acceptedUnitIds.length > 0
        ? { accepted_unit_ids: acceptedUnitIds }
        : { accepted_ids: requestPreviews.map((preview) => preview.id) };

    setCommitState((current) => ({
      ...current,
      executionId: requestExecutionId,
      committing: true,
      reverting: false,
      error: null,
      linkPreviews: null,
    }));
    try {
      const response = await commitExecutionOutputs({
        executionId: requestExecutionId,
        idempotencyKey: requestIdempotencyKey,
        body,
      });
      const nextCommitState = commitStateFromCommitResponse(response);
      if (!nextCommitState) {
        setCommitState((current) =>
          shouldApplyResponse(current.executionId, requestExecutionId, selectedRecordIdRef)
            ? {
                ...current,
                committing: false,
                reverting: false,
                responseCommitState: null,
                linkPreviews: null,
                error: COMMIT_STATE_SYNC_ERROR,
              }
            : current,
        );
        return;
      }
      patchCommitState(requestExecutionId, nextCommitState, upsertExecution);
      setCommitState((current) =>
        shouldApplyResponse(current.executionId, requestExecutionId, selectedRecordIdRef)
          ? {
              ...current,
              executionId: requestExecutionId,
              committing: false,
              reverting: false,
              responseCommitState: nextCommitState,
              linkPreviews: requestPreviews,
              error: null,
            }
          : current,
      );
    } catch (error) {
      setCommitState((current) =>
        shouldApplyResponse(current.executionId, requestExecutionId, selectedRecordIdRef)
          ? {
              ...current,
              committing: false,
              reverting: false,
              responseCommitState: null,
              linkPreviews: null,
              error: error instanceof Error ? error.message : "保存失败",
            }
          : current,
      );
    }
  }

  async function handleUndoCommit() {
    if (
      !selectedRecord ||
      commitState.committing ||
      commitState.reverting ||
      !effectiveCommitState ||
      effectiveCommitState.status !== "committed"
    ) {
      return;
    }
    const requestExecutionId = selectedRecord.id;
    setCommitState((current) => ({
      ...current,
      executionId: requestExecutionId,
      reverting: true,
      error: null,
    }));
    try {
      const response = await undoExecutionCommit({ executionId: requestExecutionId });
      const nextCommitState = commitStateFromCommitResponse(response);
      if (!nextCommitState) {
        setCommitState((current) =>
          shouldApplyResponse(current.executionId, requestExecutionId, selectedRecordIdRef)
            ? {
                ...current,
                reverting: false,
                responseCommitState: null,
                error: COMMIT_STATE_SYNC_ERROR,
              }
            : current,
        );
        return;
      }
      patchCommitState(requestExecutionId, nextCommitState, upsertExecution);
      setCommitState((current) =>
        shouldApplyResponse(current.executionId, requestExecutionId, selectedRecordIdRef)
          ? {
              ...current,
              reverting: false,
              responseCommitState: nextCommitState,
              linkPreviews: previews,
            }
          : current,
      );
    } catch (error) {
      setCommitState((current) =>
        shouldApplyResponse(current.executionId, requestExecutionId, selectedRecordIdRef)
          ? {
              ...current,
              reverting: false,
              error: error instanceof Error ? error.message : "撤回保存失败",
            }
          : current,
      );
    }
  }

  if (!selectedRecord || selectedRecord.status !== "completed") {
    return undefined;
  }

  return {
    committed: isExecutionCommitted(effectiveCommitState),
    discarded: isExecutionDiscarded(effectiveCommitState),
    reverted: isExecutionReverted(effectiveCommitState),
    committing: commitState.committing,
    reverting: commitState.reverting,
    error: commitState.error,
    links: commitLinks,
    canSave: saveCount > 0 && !commitFinal,
    saveCount,
    onSave: () => void handleCommit(),
    onUndo: () => void handleUndoCommit(),
  };
}

function emptyCommitState(executionId: string | null) {
  return {
    executionId,
    idempotencyKey: generateUUID(),
    committing: false,
    reverting: false,
    responseCommitState: null,
    linkPreviews: null,
    error: null,
  };
}

function patchCommitState(
  executionId: string,
  nextCommitState: ExecutionCommitState,
  upsertExecution: (record: ExecutionRecord) => void,
) {
  const recordToPatch = useExecutionStore.getState().executions.get(executionId);
  if (!recordToPatch) {
    return;
  }
  upsertExecution({
    ...recordToPatch,
    result: {
      ...(recordToPatch.result ?? {}),
      commit_state: nextCommitState,
    },
  });
}

function shouldApplyResponse(
  currentExecutionId: string | null,
  requestExecutionId: string,
  selectedRecordIdRef: RefObject<string | null>,
): boolean {
  return (
    currentExecutionId === requestExecutionId ||
    selectedRecordIdRef.current === requestExecutionId
  );
}
