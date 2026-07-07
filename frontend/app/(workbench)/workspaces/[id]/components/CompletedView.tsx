"use client";

import { useEffect, useMemo, useState } from "react";
import { resolveExecutionNextActionPresentation } from "@/lib/block-actions";
import {
  acceptedUnitIdsFromChangeSet,
  changeSetViewFromResult,
  commitPreviewsForChangeSetReview,
} from "@/lib/change-set-view";
import {
  buildCommittedRoomLinks,
  COMMIT_STATE_SYNC_ERROR,
  commitExecutionOutputs,
  commitStateFromCommitResponse,
  commitStateRoomTargets,
  type ExecutionCommitRequest,
  isExecutionDiscarded,
  isExecutionReverted,
  readCommitStateFromResult,
  resolveExecutionCommitState,
  type ExecutionCommitState,
  undoExecutionCommit,
} from "@/lib/execution-commit";
import {
  recoverableOutputRefCount,
  runtimeStatusLabel,
  safeRuntimeText,
} from "@/lib/runtime-payload-safety";
import { filterVisibleWorkspaceResultItems } from "@/lib/workspace-result-kind";
import {
  buildWorkspaceResultPreviewsFromOutputs,
  outputsWithSafeDefaultChecks,
} from "@/lib/workspace-result-preview";
import {
  PrismReviewList,
  prismReviewItemHref,
} from "@/components/prism/PrismReviewList";
import type { WorkspacePrismReviewItem } from "@/lib/api/types";
import { useExecutionStore } from "@/stores/execution-store";
import { ResultPreviewDetail } from "./result-preview/ResultPreviewDetail";
import { ResultPreviewList } from "./result-preview/ResultPreviewList";
import { WorkspaceActionLink } from "./WorkspaceActionLink";

type TaskReportLike = {
  status?: unknown;
  narrative?: unknown;
  result_summary?: unknown;
  outputs?: unknown;
  errors?: unknown;
  data?: unknown;
  review_items?: unknown;
};

export interface CompletedViewProps {
  workspaceId?: string | null;
  featureId?: string | null;
  executionId?: string | null;
  executionStatus?: string | null;
  resultSummary?: string | null;
  result?: Record<string, unknown> | null;
  reviewItems?: WorkspacePrismReviewItem[];
  nextActions?: Array<Record<string, unknown>>;
}

export function CompletedView({
  workspaceId,
  featureId,
  executionId,
  executionStatus,
  resultSummary,
  result,
  reviewItems = [],
  nextActions = [],
}: CompletedViewProps) {
  const [idempotencyKey] = useState(() => generateUUID());
  const upsertExecution = useExecutionStore((state) => state.upsertExecution);

  const taskReport = getTaskReport(result);
  const changeSet = useMemo(() => changeSetViewFromResult(result), [result]);
  const durableCommitState = readCommitStateFromResult(result);
  const effectiveReviewItems =
    reviewItems.length > 0 ? reviewItems : readReviewItems(taskReport?.review_items);
  const summary =
    safeRuntimeText(resultSummary, 220) ||
    safeRuntimeText(taskReport?.result_summary, 220) ||
    safeRuntimeText(taskReport?.narrative, 220) ||
    "运行结果已生成。";
  const taskStatus =
    readString(executionStatus) || readString(taskReport?.status) || "completed";
  const allowAcceptAll = taskStatus === "completed";
  const taskOutputs = useMemo(
    () => outputsWithSafeDefaultChecks(taskReport?.outputs, allowAcceptAll),
    [allowAcceptAll, taskReport?.outputs],
  );
  const rawPreviews = useMemo(
    () => buildWorkspaceResultPreviewsFromOutputs(taskOutputs),
    [taskOutputs],
  );
  const previews = useMemo(
    () => filterVisibleWorkspaceResultItems(rawPreviews),
    [rawPreviews],
  );
  const [selectedPreviewId, setSelectedPreviewId] = useState<string | null>(null);
  useEffect(() => {
    if (previews.length === 0) {
      setSelectedPreviewId(null);
      return;
    }
    setSelectedPreviewId((current) =>
      current && previews.some((preview) => preview.id === current)
        ? current
        : previews[0].id,
    );
  }, [previews]);
  const selectedPreview =
    previews.find((preview) => preview.id === selectedPreviewId) ??
    previews[0] ??
    null;
  const [localCommitState, setLocalCommitState] =
    useState<ExecutionCommitState | null>(null);
  const [committing, setCommitting] = useState(false);
  const [reverting, setReverting] = useState(false);
  const [commitError, setCommitError] = useState<string | null>(null);
  const effectiveCommitState = resolveExecutionCommitState({
    localCommitState,
    durableCommitState,
  });
  const commitFinal = Boolean(effectiveCommitState);
  const discarded = isExecutionDiscarded(effectiveCommitState);
  const reverted = isExecutionReverted(effectiveCommitState);
  const commitLinks = useMemo(
    () =>
      buildCommittedRoomLinks({
        workspaceId,
        previews,
        roomTargets: commitStateRoomTargets(effectiveCommitState),
      }),
    [effectiveCommitState, previews, workspaceId],
  );
  useEffect(() => {
    setLocalCommitState(null);
    setCommitting(false);
    setReverting(false);
    setCommitError(null);
  }, [executionId]);
  const acceptedCommitPreviews = useMemo(
    () =>
      commitPreviewsForChangeSetReview({
        changeSet,
        previews: rawPreviews,
        visiblePreviews: previews,
      }),
    [changeSet, previews, rawPreviews],
  );
  const acceptedUnitIds = useMemo(
    () => acceptedUnitIdsFromChangeSet(changeSet),
    [changeSet],
  );
  const saveCount = changeSet
    ? acceptedUnitIds.length
    : acceptedCommitPreviews.length;
  const taskErrors = taskReport?.errors;
  const errorItems = Array.isArray(taskErrors) ? taskErrors.slice(0, 3) : [];
  const actionContext = getCompletedActionContext({
    workspaceId,
    featureId,
    executionId,
    reviewItems: effectiveReviewItems,
    nextActions,
  });
  const defaultReviewActionHref =
    workspaceId && actionContext.reviewItems.length > 0
      ? prismReviewItemHref(workspaceId, actionContext.reviewItems[0])
      : null;
  const shouldShowDefaultReviewAction =
    defaultReviewActionHref !== null &&
    !actionContext.actions.some(
      (action) =>
        action.href === defaultReviewActionHref || action.label === "预览待复核修改",
    );
  const completedResultLines = buildCompletedResultStatusLines({
    result,
    taskReport,
    taskStatus,
  });
  const shouldShowWritebackControls =
    Boolean(executionId) &&
    (previews.length > 0 ||
      saveCount > 0 ||
      commitFinal ||
      Boolean(commitError) ||
      !allowAcceptAll);
  const writebackControls = shouldShowWritebackControls ? (
    <div style={{ marginBottom: 12 }}>
      <div
        style={{
          fontSize: 12,
          fontWeight: 600,
          color: "var(--wjn-text)",
          marginBottom: 8,
        }}
      >
        工作区写入
      </div>
      {!allowAcceptAll ? (
        <div style={styles.partialNotice}>
          本次运行未完整完成，候选结果只作为证据预览；需要继续处理时，请在左侧补充指令。
        </div>
      ) : null}
      {allowAcceptAll ? (
        <div style={styles.writebackStatus}>
          <span style={styles.writebackLabel}>
            {reverting
              ? "正在撤回本次保存..."
              : reverted
                ? "已撤回本次保存"
                : discarded
                  ? "已暂不保存"
                  : commitFinal
                    ? "已写入工作区"
                    : committing
                      ? "正在写入工作区..."
                      : commitError
                        ? "保存状态异常"
                        : "待复核保存"}
          </span>
          {!commitFinal && saveCount > 0 ? (
            <button
              type="button"
              onClick={commitSelected}
              disabled={committing || reverting}
              style={styles.inlineGhostButton}
            >
              {committing
                ? "保存中..."
                : commitError
                  ? `重试保存（${saveCount} 项）`
                  : `保存到工作区（${saveCount} 项）`}
            </button>
          ) : null}
          {effectiveCommitState?.status === "committed" ? (
            <button
              type="button"
              onClick={undoCommit}
              disabled={reverting}
              style={styles.inlineGhostButton}
            >
              {reverting ? "撤回中..." : "撤回本次保存"}
            </button>
          ) : null}
        </div>
      ) : null}
      {commitError ? (
        <div style={styles.commitError}>{commitError}</div>
      ) : null}
      {commitLinks.length > 0 ? (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            marginTop: 10,
          }}
        >
          {commitLinks.map((link) => (
            <WorkspaceActionLink
              key={link.key}
              href={link.href}
              style={styles.reviewActionLink}
            >
              {link.label}
            </WorkspaceActionLink>
          ))}
        </div>
      ) : null}
    </div>
  ) : null;

  async function commitSelected() {
    if (
      !executionId ||
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
        executionId,
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
      const currentRecord = useExecutionStore.getState().executions.get(executionId);
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
          : "保存失败，请稍后重试",
      );
    } finally {
      setCommitting(false);
    }
  }

  async function undoCommit() {
    if (
      !executionId ||
      reverting ||
      !effectiveCommitState ||
      effectiveCommitState.status !== "committed"
    ) {
      return;
    }
    setCommitError(null);
    setReverting(true);
    try {
      const response = await undoExecutionCommit({ executionId });
      const nextCommitState = commitStateFromCommitResponse(response);
      if (!nextCommitState) {
        setLocalCommitState(null);
        setCommitError(COMMIT_STATE_SYNC_ERROR);
        return;
      }
      setLocalCommitState(nextCommitState);
      const currentRecord = useExecutionStore.getState().executions.get(executionId);
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

  return (
    <div
      style={{
        fontFamily: "var(--wjn-font-sans)",
        color: "var(--wjn-text)",
      }}
    >
      {/* Summary text */}
      <div
        style={{
          fontSize: 13,
          lineHeight: 1.5,
          color: "var(--wjn-text-secondary)",
          marginBottom: previews.length > 0 ? 12 : 8,
        }}
      >
        {summary}
      </div>

      {previews.length > 0 && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 260px), 1fr))",
            gap: 12,
            marginBottom: 12,
          }}
        >
          <ResultPreviewList
            previews={previews}
            selectedId={selectedPreview?.id ?? null}
            onSelect={setSelectedPreviewId}
          />
          <ResultPreviewDetail
            preview={selectedPreview}
            footer={
              executionId ||
              actionContext.actions.length > 0 ||
              actionContext.reviewItems.length > 0 ? (
                <div style={styles.actionFooter}>
                  {writebackControls}

                  {(actionContext.reviewItems.length > 0 ||
                    actionContext.actions.length > 0) && (
                    <div
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        color: "var(--wjn-text)",
                        marginBottom: actionContext.reviewItems.length > 0 ? 8 : 6,
                      }}
                    >
                      {actionContext.reviewItems.length > 0
                        ? "待复核修改"
                        : "下一步操作"}
                    </div>
                  )}

                  {actionContext.reviewItems.length > 0 && (
                    <>
                      <PrismReviewList
                        className={actionContext.actions.length > 0 ? "mb-3" : undefined}
                        items={actionContext.reviewItems}
                      />
                      {shouldShowDefaultReviewAction ? (
                        <div style={styles.reviewDefaultActions}>
                          <WorkspaceActionLink
                            href={defaultReviewActionHref}
                            style={styles.reviewActionLink}
                          >
                            预览待复核修改
                          </WorkspaceActionLink>
                        </div>
                      ) : null}
                    </>
                  )}

                  {actionContext.actions.length > 0 && (
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: 8,
                      }}
                    >
                      {actionContext.actions.map((action) =>
                        action.href ? (
                          <WorkspaceActionLink
                            key={action.key}
                            href={action.href}
                            style={styles.reviewActionLink}
                          >
                            {action.label}
                          </WorkspaceActionLink>
                        ) : (
                          <span
                            key={action.key}
                            style={styles.reviewActionBadge}
                          >
                            {action.label}
                          </span>
                        ),
                      )}
                    </div>
                  )}
                </div>
              ) : null
            }
          />
        </div>
      )}

      {errorItems.length > 0 && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 6,
            marginBottom: 12,
          }}
        >
          {errorItems.map((error, i) => {
            const label = buildCompletedErrorSummary(error, i);
            return (
              <div
                key={i}
                style={{
                  padding: "6px 10px",
                  borderRadius: "var(--wjn-radius-md)",
                  background: "rgba(220, 38, 38, 0.06)",
                  border: "1px solid rgba(220, 38, 38, 0.12)",
                  color: "var(--wjn-error)",
                  fontSize: 11.5,
                  lineHeight: 1.45,
                }}
              >
                {label}
              </div>
            );
          })}
        </div>
      )}

      {previews.length === 0 &&
        (writebackControls ||
          actionContext.actions.length > 0 ||
          actionContext.reviewItems.length > 0) && (
        <div
          style={{
            marginBottom: 12,
            padding: "10px 12px",
            borderRadius: "var(--wjn-radius-md)",
            background: "var(--wjn-accent-soft)",
            border: "1px solid var(--wjn-accent-soft)",
          }}
        >
          {writebackControls}

          {actionContext.reviewItems.length > 0 ||
          actionContext.actions.length > 0 ? (
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "var(--wjn-text)",
                marginBottom: actionContext.reviewItems.length > 0 ? 8 : 0,
              }}
            >
              {actionContext.reviewItems.length > 0 ? "待复核修改" : "下一步操作"}
            </div>
          ) : null}

          {actionContext.reviewItems.length > 0 && (
            <>
              <PrismReviewList
                className={actionContext.actions.length > 0 ? "mb-3" : undefined}
                items={actionContext.reviewItems}
              />
              {shouldShowDefaultReviewAction ? (
                <div style={styles.reviewDefaultActions}>
                  <WorkspaceActionLink
                    href={defaultReviewActionHref}
                    style={styles.reviewActionLink}
                  >
                    预览待复核修改
                  </WorkspaceActionLink>
                </div>
              ) : null}
            </>
          )}

          {actionContext.actions.length > 0 && (
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 8,
              }}
            >
              {actionContext.actions.map((action) =>
                action.href ? (
                  <WorkspaceActionLink
                    key={action.key}
                    href={action.href}
                    style={styles.reviewActionLink}
                  >
                    {action.label}
                  </WorkspaceActionLink>
                ) : (
                  <span
                    key={action.key}
                    style={styles.reviewActionBadge}
                  >
                    {action.label}
                  </span>
                ),
              )}
            </div>
          )}
        </div>
      )}

      {result && previews.length === 0 && (
        <div style={styles.safeResultSummary}>
          {completedResultLines.map((line) => (
            <div key={line}>{line}</div>
          ))}
        </div>
      )}
    </div>
  );
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

function readString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed || null;
}

function getTaskReport(result?: Record<string, unknown> | null): TaskReportLike | null {
  if (!result || typeof result !== "object") return null;
  const nested = result.task_report;
  if (nested && typeof nested === "object" && !Array.isArray(nested)) {
    return nested as TaskReportLike;
  }
  return result as TaskReportLike;
}

function readReviewItems(value: unknown): WorkspacePrismReviewItem[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => readObject(item))
    .filter((item): item is Record<string, unknown> => item !== null)
    .map((item) => item as unknown as WorkspacePrismReviewItem);
}

function buildCompletedResultStatusLines({
  result,
  taskReport,
  taskStatus,
}: {
  result?: Record<string, unknown> | null;
  taskReport: TaskReportLike | null;
  taskStatus: string;
}): string[] {
  const taskReportRecord = readObject(taskReport);
  const outputCount = Array.isArray(taskReport?.outputs) ? taskReport.outputs.length : 0;
  const errorCount = Array.isArray(taskReport?.errors) ? taskReport.errors.length : 0;
  const refCount = recoverableOutputRefCount(
    taskReportRecord?.output_refs,
    taskReportRecord?.output_ref,
    result?.output_refs,
    result?.output_ref,
  );
  return [
    `状态：${runtimeStatusLabel(taskStatus)}`,
    outputCount > 0 ? `候选结果：${outputCount} 项` : null,
    refCount > 0 ? `可恢复引用：${refCount} 个` : null,
    errorCount > 0 ? `需处理事项：${errorCount} 项` : null,
  ].filter((line): line is string => Boolean(line));
}

function buildCompletedErrorSummary(error: unknown, index: number): string {
  const item = readObject(error);
  const safeMessage =
    safeRuntimeText(item?.error, 140) ??
    safeRuntimeText(item?.message, 140) ??
    "运行问题已记录";
  const context = [
    safeRuntimeText(item?.phase, 40),
    safeRuntimeText(item?.task, 60),
  ].filter((value): value is string => Boolean(value));
  return [
    `问题 ${index + 1}`,
    context.length ? context.join(" / ") : null,
    safeMessage,
  ].filter((value): value is string => Boolean(value)).join("：");
}

type PrismReviewAction = {
  key: string;
  label: string;
  href: string | null;
};

function getCompletedActionContext(options: {
  workspaceId?: string | null;
  featureId?: string | null;
  executionId?: string | null;
  reviewItems: WorkspacePrismReviewItem[];
  nextActions: Array<Record<string, unknown>>;
}): {
  actions: PrismReviewAction[];
  reviewItems: WorkspacePrismReviewItem[];
} {
  const {
    workspaceId,
    featureId,
    executionId,
    reviewItems,
    nextActions,
  } = options;

  const actions = nextActions
    .map((item, index) => {
      const action = readObject(item);
      if (!action) {
        return null;
      }
      const presentation = resolveExecutionNextActionPresentation({
        actionRecord: action,
        workspaceId,
        defaultFeatureId: featureId,
        defaultExecutionId: executionId,
      });
      if (!presentation) {
        return null;
      }
      return {
        key: `${presentation.action}:${index}`,
        label: presentation.label,
        href: presentation.href,
      };
    })
    .filter((item): item is PrismReviewAction => item !== null);

  return { actions, reviewItems };
}

function readObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

const styles: Record<string, React.CSSProperties> = {
  safeResultSummary: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
    marginTop: 8,
    padding: "8px 10px",
    borderRadius: "var(--wjn-radius-md)",
    background: "var(--wjn-surface-subtle)",
    border: "1px solid var(--wjn-line)",
    color: "var(--wjn-text-secondary)",
    fontSize: 12,
    lineHeight: 1.45,
  },
  actionFooter: {
    paddingTop: 12,
    borderTop: "1px solid rgba(20, 20, 30, 0.08)",
  },
  reviewDefaultActions: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 10,
    marginBottom: 10,
  },
  commitError: {
    marginTop: 10,
    padding: "8px 10px",
    borderRadius: "var(--wjn-radius-md)",
    background: "rgba(220, 38, 38, 0.06)",
    border: "1px solid rgba(220, 38, 38, 0.12)",
    color: "var(--wjn-error)",
    fontSize: 11.5,
    lineHeight: 1.45,
  },
  partialNotice: {
    padding: "8px 10px",
    borderRadius: "var(--wjn-radius-md)",
    background: "var(--wjn-review-soft)",
    border: "1px solid rgba(198, 138, 26, 0.16)",
    color: "var(--wjn-review)",
    fontSize: 11.5,
    lineHeight: 1.45,
    marginBottom: 10,
  },
  writebackStatus: {
    display: "flex",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 8,
    minHeight: 30,
  },
  writebackLabel: {
    color: "var(--wjn-success)",
    fontSize: 12,
    fontWeight: 650,
  },
  inlineGhostButton: {
    height: 28,
    padding: "0 9px",
    borderRadius: "var(--wjn-radius-pill)",
    border: "1px solid rgba(20,20,30,0.1)",
    background: "var(--wjn-surface)",
    color: "var(--wjn-text-secondary)",
    fontSize: 11.5,
    fontWeight: 600,
    cursor: "pointer",
  },
  reviewActionLink: {
    display: "inline-flex",
    alignItems: "center",
    padding: "4px 10px",
    borderRadius: "var(--wjn-radius-pill)",
    background: "var(--wjn-accent-soft)",
    color: "var(--wjn-blue)",
    fontSize: 11.5,
    fontWeight: 500,
    lineHeight: "18px",
    textDecoration: "none",
  },
  reviewActionBadge: {
    display: "inline-flex",
    alignItems: "center",
    padding: "4px 10px",
    borderRadius: "var(--wjn-radius-pill)",
    background: "rgba(20, 20, 30, 0.06)",
    color: "var(--wjn-text-secondary)",
    fontSize: 11.5,
    fontWeight: 500,
    lineHeight: "18px",
  },
};
