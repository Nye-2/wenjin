"use client";

import { useMemo, useState } from "react";

import {
  buildCommittedRoomLinks,
  COMMIT_STATE_SYNC_ERROR,
  commitExecutionOutputs,
  commitStateFromCommitResponse,
  commitStateRoomTargets,
  type ExecutionCommitRequest,
  isExecutionCommitted,
  isExecutionDiscarded,
  isExecutionReverted,
  readCommitStateFromResult,
  resolveExecutionCommitState,
  type ExecutionCommitState,
  undoExecutionCommit,
} from "@/lib/execution-commit";
import {
  acceptedUnitIdsFromChangeSet,
  changeSetViewFromResult,
  commitPreviewsForChangeSetReview,
} from "@/lib/change-set-view";
import { safeRuntimeText } from "@/lib/runtime-payload-safety";
import {
  filterVisibleWorkspaceResultItems,
  groupWorkspaceResultPreviews,
} from "@/lib/workspace-result-kind";
import {
  buildWorkspaceResultPreviewsFromOutputs,
  outputsWithSafeDefaultChecks,
} from "@/lib/workspace-result-preview";
import {
  PrismReviewList,
  prismReviewItemHref,
} from "@/components/prism/PrismReviewList";
import type { WorkspacePrismReviewItem } from "@/lib/api/types";
import type { ResultCardData } from "@/stores/chat-store";
import { useExecutionStore } from "@/stores/execution-store";
import { useRunUiStore } from "@/stores/run-ui-store";
import { useWorkbenchLayoutStore } from "@/stores/workbench-layout-store";
import { WorkspaceActionLink } from "./WorkspaceActionLink";

function isPrismReviewItem(item: WorkspacePrismReviewItem): boolean {
  return item.kind === "prism_file_change" || item.target?.kind === "prism_file_change";
}

function reviewNotice(items: WorkspacePrismReviewItem[]): string {
  const prismCount = items.filter(isPrismReviewItem).length;
  const artifactCount = items.filter((item) => item.kind === "sandbox_artifact").length;
  if (prismCount === items.length) {
    return `写作台有 ${items.length} 项待复核修改`;
  }
  if (artifactCount === items.length) {
    return `结果有 ${items.length} 项可查看`;
  }
  return `有 ${items.length} 项待复核`;
}

interface ResultCardProps {
  data: ResultCardData;
  workspaceId?: string;
}

export function ResultCard({ data, workspaceId }: ResultCardProps) {
  const {
    execution_id,
    capability_name,
    status,
    duration_seconds,
    narrative,
    outputs,
  } = data;
  const canSaveAll = status === "completed";
  const safeOutputs = useMemo(
    () => outputsWithSafeDefaultChecks(outputs, canSaveAll),
    [canSaveAll, outputs],
  );

  const previews = useMemo(
    () => buildWorkspaceResultPreviewsFromOutputs(safeOutputs),
    [safeOutputs],
  );
  const visiblePreviews = useMemo(
    () => filterVisibleWorkspaceResultItems(previews),
    [previews],
  );
  const previewGroups = useMemo(
    () => groupWorkspaceResultPreviews(visiblePreviews),
    [visiblePreviews],
  );
  const representativePreviews = useMemo(
    () => visiblePreviews.slice(0, 3),
    [visiblePreviews],
  );
  const narrativeText =
    safeRuntimeText(narrative, 220) ?? (narrative ? "运行结果已生成。" : null);
  const reviewItems = data.review_items ?? [];
  const firstPrismReviewItem = reviewItems.find(isPrismReviewItem);
  const selectRun = useWorkbenchLayoutStore((state) => state.selectRun);
  const setActiveWorkbenchTab = useWorkbenchLayoutStore(
    (state) => state.setActiveWorkbenchTab,
  );
  const setWorkbenchFullscreen = useWorkbenchLayoutStore(
    (state) => state.setWorkbenchFullscreen,
  );
  const focusPreviewItem = useRunUiStore((state) => state.focusPreviewItem);
  const executionResult = useExecutionStore(
    (state) => state.executions.get(execution_id)?.result,
  );
  const changeSet = useMemo(
    () => changeSetViewFromResult(executionResult ?? data),
    [data, executionResult],
  );
  const upsertExecution = useExecutionStore((state) => state.upsertExecution);
  const [idempotencyKey] = useState(() => generateUUID());
  const [localCommitState, setLocalCommitState] =
    useState<ExecutionCommitState | null>(null);
  const [committing, setCommitting] = useState(false);
  const [reverting, setReverting] = useState(false);
  const [commitError, setCommitError] = useState<string | null>(null);
  const durableCommitState = readCommitStateFromResult(executionResult);
  const dataCommitState = readCommitStateFromResult(data);
  const effectiveCommitState = resolveExecutionCommitState({
    localCommitState,
    durableCommitState,
    fallbackCommitState: dataCommitState,
  });
  const committed = isExecutionCommitted(effectiveCommitState);
  const discarded = isExecutionDiscarded(effectiveCommitState);
  const reverted = isExecutionReverted(effectiveCommitState);
  const commitFinal = Boolean(effectiveCommitState);
  const commitLinks = useMemo(
    () =>
      buildCommittedRoomLinks({
        workspaceId,
        previews,
        roomTargets: commitStateRoomTargets(effectiveCommitState),
      }),
    [effectiveCommitState, previews, workspaceId],
  );
  const acceptedCommitPreviews = useMemo(
    () =>
      commitPreviewsForChangeSetReview({
        changeSet,
        previews,
        visiblePreviews,
      }),
    [changeSet, previews, visiblePreviews],
  );
  const acceptedUnitIds = useMemo(
    () => acceptedUnitIdsFromChangeSet(changeSet),
    [changeSet],
  );
  const saveCount = changeSet
    ? acceptedUnitIds.length
    : acceptedCommitPreviews.length;
  const receiptPendingCount =
    visiblePreviews.length > 0 ? visiblePreviews.length : saveCount;
  const receiptResultCount =
    commitFinal
      ? committedResultCount(effectiveCommitState) ?? receiptPendingCount
      : receiptPendingCount;
  const receiptStatusText = commitFinal
    ? discarded
      ? `${receiptPendingCount} 项结果已暂不保存`
      : reverted
        ? `${receiptResultCount} 项结果已撤回`
        : `${receiptResultCount} 项结果已写入`
    : `${receiptPendingCount} 项结果待复核保存`;
  const showResultPackage =
    visiblePreviews.length > 0 ||
    (canSaveAll && Boolean(workspaceId) && saveCount > 0) ||
    commitFinal ||
    Boolean(commitError);

  async function commitSelected() {
    if (
      !workspaceId ||
      commitFinal ||
      committing ||
      reverting ||
      saveCount === 0
    ) {
      return;
    }
    const body: ExecutionCommitRequest =
      changeSet && acceptedUnitIds.length > 0
        ? { accepted_unit_ids: acceptedUnitIds }
        : { accepted_ids: acceptedCommitPreviews.map((preview) => preview.id) };
    setCommitError(null);
    setCommitting(true);
    try {
      const response = await commitExecutionOutputs({
        executionId: execution_id,
        idempotencyKey,
        body,
      });
      const nextCommitState = commitStateFromCommitResponse(response);
      if (!nextCommitState) {
        setLocalCommitState(null);
        setCommitError(COMMIT_STATE_SYNC_ERROR);
        return;
      }
      setLocalCommitState(nextCommitState);
      const currentRecord =
        useExecutionStore.getState().executions.get(execution_id);
      if (currentRecord) {
        upsertExecution({
          ...currentRecord,
          result: {
            ...(currentRecord.result ?? {}),
            commit_state: nextCommitState,
          },
        });
      }
    } catch (error) {
      setCommitError(
        error instanceof Error && !error.message.startsWith("Failed")
          ? error.message
          : "保存结果失败，请稍后重试",
      );
    } finally {
      setCommitting(false);
    }
  }

  async function undoCommit() {
    if (!committed || reverting) {
      return;
    }
    setCommitError(null);
    setReverting(true);
    try {
      const response = await undoExecutionCommit({ executionId: execution_id });
      const nextCommitState = commitStateFromCommitResponse(response);
      if (!nextCommitState) {
        setLocalCommitState(null);
        setCommitError(COMMIT_STATE_SYNC_ERROR);
        return;
      }
      setLocalCommitState(nextCommitState);
      const currentRecord =
        useExecutionStore.getState().executions.get(execution_id);
      if (currentRecord) {
        upsertExecution({
          ...currentRecord,
          result: {
            ...(currentRecord.result ?? {}),
            commit_state: nextCommitState,
          },
        });
      }
    } catch (error) {
      setCommitError(
        error instanceof Error && !error.message.startsWith("Failed")
          ? error.message
          : "撤回保存失败，请稍后重试",
      );
    } finally {
      setReverting(false);
    }
  }

  function openRunSurface() {
    selectRun(execution_id);
    const previewItemId = data.previewItemId ?? data.preview_item_id ?? null;
    if (previewItemId) {
      focusPreviewItem(previewItemId);
    } else {
      focusPreviewItem(null);
    }
    setActiveWorkbenchTab("run");
    setWorkbenchFullscreen(true);
  }

  const statusLabel =
    status === "completed" ? "完成" : status === "failed_partial" ? "部分完成" : "已取消";
  const statusIconColor =
    status === "completed"
      ? "var(--wjn-success)"
      : status === "failed_partial"
        ? "var(--wjn-review)"
        : "var(--wjn-error)";

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <span style={{ ...styles.statusIcon, color: statusIconColor }}>
          {status === "completed" ? "✓" : status === "failed_partial" ? "!" : "×"}
        </span>
        <span style={styles.headerTitle}>
          {capability_name ?? "运行"} {statusLabel}
        </span>
        {duration_seconds != null ? (
          <span style={styles.duration}>{duration_seconds}s</span>
        ) : null}
      </div>

      {narrativeText ? <div style={styles.narrative}>{narrativeText}</div> : null}
      {!canSaveAll && visiblePreviews.length > 0 ? (
        <div style={styles.partialNotice}>
          本次运行未完整完成，请先查看运行详情；需要保留的内容可继续在左侧对话中处理。
        </div>
      ) : null}

      {reviewItems.length ? (
        <div style={styles.reviewItems}>
          <div style={styles.prismNotice}>
            {reviewNotice(reviewItems)}
          </div>
          <PrismReviewList items={reviewItems} />
          {workspaceId && firstPrismReviewItem ? (
            <WorkspaceActionLink
              href={prismReviewItemHref(workspaceId, firstPrismReviewItem)}
              style={styles.savedLink}
            >
              预览待复核修改
            </WorkspaceActionLink>
          ) : null}
        </div>
      ) : null}

      {showResultPackage ? (
        <div style={styles.packageShell}>
          <div style={styles.packageHeader}>
            <div style={styles.receiptMeta}>
              <span>{receiptStatusText}</span>
            </div>
            <div style={styles.groupStats}>
              {previewGroups.map((group) => (
                <span
                  key={group.kind}
                  style={{
                    ...styles.groupStat,
                    color: group.meta.accent,
                    background: group.meta.tint,
                    border: `1px solid ${group.meta.border}`,
                  }}
                >
                  {group.meta.groupLabel}
                  <strong style={styles.groupStatCount}>{group.items.length}</strong>
                </span>
              ))}
            </div>
          </div>

          {representativePreviews.length > 0 ? (
            <div style={styles.representativeList}>
              {representativePreviews.map((preview) => {
                const groupMeta = previewGroups.find(
                  (group) => group.kind === preview.kind,
                )?.meta;
                return (
                  <div key={preview.id} style={styles.representativeItem}>
                    {preview.kind === "figure" ? (
                      <span style={styles.figureThumb} aria-hidden="true">
                        {[18, 28, 22].map((height) => (
                          <span
                            key={height}
                            style={{
                              ...styles.figureThumbBar,
                              height,
                              background:
                                groupMeta?.accent ?? "var(--wjn-blue)",
                            }}
                          />
                        ))}
                      </span>
                    ) : null}
                    <span
                      style={{
                        ...styles.previewKindBadge,
                        color: groupMeta?.accent ?? "var(--wjn-text-secondary)",
                        background: groupMeta?.tint ?? "rgba(20,20,30,0.06)",
                        border: `1px solid ${groupMeta?.border ?? "rgba(20,20,30,0.1)"}`,
                      }}
                    >
                      {groupMeta?.shortLabel ?? "输出"}
                    </span>
                    <div style={styles.representativeText}>
                      <div style={styles.previewTitle}>{preview.title}</div>
                      {preview.subtitle ? (
                        <div style={styles.previewSubtitle}>{preview.subtitle}</div>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : null}

          <div style={styles.actionRow}>
            <button
              type="button"
              onClick={openRunSurface}
              style={styles.primaryButton}
            >
              查看运行
            </button>
            {canSaveAll && !commitFinal ? (
              <span style={styles.statusText}>复核后保存到工作区，也可查看运行详情</span>
            ) : null}
            {canSaveAll && !commitFinal && workspaceId && saveCount > 0 ? (
              <button
                type="button"
                onClick={commitSelected}
                disabled={committing || reverting}
                style={{
                  ...styles.secondaryButton,
                  ...(committing ? styles.buttonDisabled : null),
                }}
              >
                {committing
                  ? "保存中..."
                  : commitError
                    ? `重试保存（${saveCount} 项）`
                    : `保存到工作区（${saveCount} 项）`}
              </button>
            ) : null}
            {discarded ? (
              <span style={styles.statusText}>已暂不保存</span>
            ) : null}
            {reverted ? (
              <span style={styles.statusText}>已撤回本次保存</span>
            ) : null}
            {canSaveAll && committed ? (
              <button
                type="button"
                onClick={undoCommit}
                disabled={reverting}
                style={{
                  ...styles.ghostButton,
                  ...(reverting ? styles.buttonDisabled : null),
                }}
              >
                {reverting ? "撤回中..." : "撤回本次保存"}
              </button>
            ) : null}
          </div>
          {commitError ? (
            <div style={styles.commitError}>{commitError}</div>
          ) : null}
          {commitLinks.length > 0 ? (
            <div style={styles.savedLinks}>
              {commitLinks.map((link) => (
                <WorkspaceActionLink
                  key={link.key}
                  href={link.href}
                  style={styles.savedLink}
                >
                  {link.label}
                </WorkspaceActionLink>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    padding: "16px",
    background: "var(--wjn-surface)",
    borderRadius: "var(--wjn-radius-lg)",
    border: "1px solid var(--wjn-line)",
    boxShadow: "var(--wjn-shadow-sm)",
    margin: "8px 0",
    fontFamily: "var(--wjn-font-sans)",
    fontSize: 13,
    color: "var(--wjn-text)",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    marginBottom: 4,
    fontWeight: 500,
  },
  statusIcon: {
    fontSize: 14,
  },
  headerTitle: {
    fontVariantNumeric: "tabular-nums",
  },
  duration: {
    marginLeft: "auto",
    fontSize: 12,
    color: "var(--wjn-text-muted)",
    fontVariantNumeric: "tabular-nums",
  },
  narrative: {
    color: "var(--wjn-text-secondary)",
    fontSize: 12.5,
    marginBottom: "12px",
    lineHeight: 1.5,
  },
  partialNotice: {
    padding: "8px 10px",
    borderRadius: "var(--wjn-radius-md)",
    background: "var(--wjn-review-soft)",
    border: "1px solid rgba(198, 138, 26, 0.16)",
    color: "var(--wjn-review)",
    fontSize: 12,
    lineHeight: 1.45,
    marginBottom: "12px",
  },
  reviewItems: {
    display: "grid",
    gap: 8,
    marginBottom: "12px",
  },
  prismNotice: {
    fontSize: 12.5,
    fontWeight: 650,
    color: "var(--wjn-blue)",
  },
  packageShell: {
    display: "grid",
    gap: 12,
  },
  packageHeader: {
    display: "grid",
    gap: 8,
  },
  receiptMeta: {
    fontSize: 12,
    color: "var(--wjn-text-muted)",
  },
  groupStats: {
    display: "flex",
    flexWrap: "wrap",
    gap: 7,
  },
  groupStat: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    height: 24,
    padding: "0 9px",
    borderRadius: "var(--wjn-radius-pill)",
    border: "1px solid",
    fontSize: 11.5,
    fontWeight: 750,
  },
  groupStatCount: {
    fontSize: 11,
    fontWeight: 800,
    fontVariantNumeric: "tabular-nums",
  },
  representativeList: {
    display: "grid",
    gap: 7,
  },
  representativeItem: {
    display: "flex",
    alignItems: "flex-start",
    gap: 9,
    padding: "8px 9px",
    borderRadius: "var(--wjn-radius-md)",
    border: "1px solid rgba(20,20,30,0.06)",
    background: "var(--wjn-surface-subtle)",
  },
  representativeText: {
    minWidth: 0,
  },
  actionRow: {
    display: "flex",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 8,
  },
  primaryButton: {
    border: "1px solid var(--wjn-blue)",
    background: "var(--wjn-blue)",
    color: "#fff",
    borderRadius: "var(--wjn-radius-pill)",
    padding: "7px 12px",
    fontSize: 12.5,
    fontWeight: 650,
    cursor: "pointer",
  },
  secondaryButton: {
    border: "1px solid var(--wjn-accent-line)",
    background: "var(--wjn-accent-soft)",
    color: "var(--wjn-blue)",
    borderRadius: "var(--wjn-radius-pill)",
    padding: "7px 12px",
    fontSize: 12.5,
    fontWeight: 650,
    cursor: "pointer",
  },
  statusText: {
    color: "var(--wjn-text-muted)",
    fontSize: 12,
    fontWeight: 650,
  },
  ghostButton: {
    border: "1px solid rgba(20, 20, 30, 0.08)",
    background: "var(--wjn-surface)",
    color: "var(--wjn-text-secondary)",
    borderRadius: "var(--wjn-radius-pill)",
    padding: "7px 12px",
    fontSize: 12.5,
    fontWeight: 550,
    cursor: "pointer",
  },
  buttonDisabled: {
    opacity: 0.58,
    cursor: "default",
  },
  previewKindBadge: {
    width: 38,
    height: 22,
    flexShrink: 0,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: "var(--wjn-radius-pill)",
    border: "1px solid",
    fontSize: 11,
    fontWeight: 750,
    lineHeight: 1,
  },
  previewTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: "var(--wjn-text)",
    marginBottom: 4,
  },
  previewSubtitle: {
    fontSize: 12,
    color: "var(--wjn-text-muted)",
    marginBottom: 4,
  },
  previewMetaLine: {
    fontSize: 11.5,
    color: "var(--wjn-text-muted)",
    fontFamily: "var(--wjn-font-mono)",
    wordBreak: "break-word",
  },
  figureThumb: {
    width: 42,
    height: 34,
    flexShrink: 0,
    display: "inline-flex",
    alignItems: "end",
    justifyContent: "center",
    gap: 4,
    padding: "0 6px 6px",
    borderRadius: "var(--wjn-radius)",
    border: "1px solid rgba(20,20,30,0.08)",
    background: "var(--wjn-surface-subtle)",
  },
  figureThumbBar: {
    width: 6,
    opacity: 0.62,
    borderRadius: "3px 3px 0 0",
  },
  commitError: {
    padding: "8px 10px",
    borderRadius: "var(--wjn-radius-md)",
    background: "rgba(220, 38, 38, 0.06)",
    border: "1px solid rgba(220, 38, 38, 0.12)",
    color: "var(--wjn-error)",
    fontSize: 11.5,
    lineHeight: 1.45,
  },
  savedLinks: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  savedLink: {
    display: "inline-flex",
    alignItems: "center",
    padding: "6px 12px",
    borderRadius: "var(--wjn-radius-pill)",
    background: "rgba(59, 130, 246, 0.08)",
    border: "1px solid rgba(59, 130, 246, 0.16)",
    color: "var(--wjn-blue)",
    fontSize: 12.5,
    fontWeight: 500,
    textDecoration: "none",
  },
};

function committedResultCount(state: ExecutionCommitState | null): number | null {
  if (!state) return null;
  const total = Object.values(state.counts).reduce((sum, count) => sum + count, 0);
  return total > 0 ? total : null;
}

function generateUUID(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
