"use client";

import { useEffect, useMemo, useState } from "react";
import { resolveExecutionNextActionPresentation } from "@/lib/block-actions";
import {
  buildCommittedRoomLinks,
  commitExecutionOutputs,
  type CommittedRoomLink,
} from "@/lib/execution-commit";
import { buildWorkspaceResultPreviewsFromOutputs } from "@/lib/workspace-result-preview";
import {
  PrismReviewList,
  prismReviewItemHref,
} from "@/components/prism/PrismReviewList";
import type { WorkspacePrismReviewItem } from "@/lib/api/types";
import { CommitActionBar } from "./result-preview/CommitActionBar";
import { ResultPreviewDetail } from "./result-preview/ResultPreviewDetail";
import { ResultPreviewList } from "./result-preview/ResultPreviewList";
import { WorkspaceActionLink } from "./WorkspaceActionLink";

type TaskReportLike = {
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
  resultSummary?: string | null;
  result?: Record<string, unknown> | null;
  reviewItems?: WorkspacePrismReviewItem[];
  nextActions?: Array<Record<string, unknown>>;
}

export function CompletedView({
  workspaceId,
  featureId,
  executionId,
  resultSummary,
  result,
  reviewItems = [],
  nextActions = [],
}: CompletedViewProps) {
  const [showFullResult, setShowFullResult] = useState(false);
  const [idempotencyKey] = useState(() => generateUUID());

  const taskReport = getTaskReport(result);
  const effectiveReviewItems =
    reviewItems.length > 0 ? reviewItems : readReviewItems(taskReport?.review_items);
  const summary =
    resultSummary ||
    readString(taskReport?.result_summary) ||
    readString(taskReport?.narrative) ||
    "Execution completed.";
  const taskOutputs = taskReport?.outputs;
  const previews = useMemo(
    () => buildWorkspaceResultPreviewsFromOutputs(taskOutputs),
    [taskOutputs],
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
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [committed, setCommitted] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [commitLinks, setCommitLinks] = useState<CommittedRoomLink[]>([]);
  const [commitError, setCommitError] = useState<string | null>(null);
  useEffect(() => {
    setCheckedIds(
      new Set(
        previews
          .filter((preview) => preview.defaultChecked)
          .map((preview) => preview.id),
      ),
    );
    setCommitted(false);
    setCommitting(false);
    setCommitLinks([]);
    setCommitError(null);
  }, [previews]);
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
        action.href === defaultReviewActionHref || action.label === "预览待确认修改",
    );

  async function commit(body: Record<string, unknown>) {
    if (!executionId || committed || committing) {
      return;
    }
    setCommitError(null);
    setCommitting(true);
    try {
      const response = await commitExecutionOutputs({
        executionId,
        idempotencyKey,
        body,
      });
      setCommitLinks(
        buildCommittedRoomLinks({
          workspaceId,
          previews,
          roomTargets: response.room_targets,
        }),
      );
      setCommitted(true);
    } catch (error) {
      setCommitLinks([]);
      setCommitted(false);
      setCommitError(
        error instanceof Error ? error.message : "Failed to save outputs",
      );
    } finally {
      setCommitting(false);
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
            gridTemplateColumns: "minmax(0, 240px) minmax(0, 1fr)",
            gap: 12,
            marginBottom: 12,
          }}
        >
          <ResultPreviewList
            previews={previews}
            selectedId={selectedPreview?.id ?? null}
            onSelect={setSelectedPreviewId}
            checkedIds={executionId ? checkedIds : undefined}
            onToggleChecked={
              executionId
                ? (id) =>
                    setCheckedIds((prev) => {
                      const next = new Set(prev);
                      if (next.has(id)) {
                        next.delete(id);
                      } else {
                        next.add(id);
                      }
                      return next;
                    })
                : undefined
            }
            disabled={committed}
          />
          <ResultPreviewDetail
            preview={selectedPreview}
            footer={
              executionId ||
              actionContext.actions.length > 0 ||
              actionContext.reviewItems.length > 0 ? (
                <div style={styles.actionFooter}>
                  {executionId ? (
                    <div style={{ marginBottom: 12 }}>
                      <div
                        style={{
                          fontSize: 12,
                          fontWeight: 600,
                          color: "var(--wjn-text)",
                          marginBottom: 8,
                        }}
                      >
                        保存到工作区
                      </div>
                      <CommitActionBar
                        committed={committed}
                        committing={committing}
                        onAcceptAll={() => commit({ accept_all: true })}
                        onAcceptSelected={() =>
                          commit({ accepted_ids: Array.from(checkedIds) })
                        }
                        onDiscard={() => commit({ accepted_ids: [] })}
                        acceptAllLabel="保存到工作区"
                        acceptSelectedLabel="仅保存勾选项"
                        discardLabel="暂不保存"
                        committedLabel="已保存到工作区"
                      />
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
                  ) : null}

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
                        ? "待确认修改"
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
                            预览待确认修改
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
            const item = error as Record<string, unknown>;
            const label =
              readString(item.error) ||
              readString(item.message) ||
              `Error ${i + 1}`;
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
        (actionContext.actions.length > 0 || actionContext.reviewItems.length > 0) && (
        <div
          style={{
            marginBottom: 12,
            padding: "10px 12px",
            borderRadius: "var(--wjn-radius-md)",
            background: "var(--wjn-accent-soft)",
            border: "1px solid var(--wjn-accent-soft)",
          }}
        >
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "var(--wjn-text)",
              marginBottom: actionContext.reviewItems.length > 0 ? 8 : 0,
            }}
          >
            {actionContext.reviewItems.length > 0 ? "待确认修改" : "下一步操作"}
          </div>

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
                    预览待确认修改
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

      {/* View full result toggle */}
      {result && previews.length === 0 && (
        <>
          <button
            onClick={() => setShowFullResult((prev) => !prev)}
            style={{
              background: "none",
              border: "none",
              padding: 0,
              color: "var(--wjn-blue)",
              fontSize: 12,
              fontWeight: 500,
              cursor: "pointer",
              fontFamily: "var(--wjn-font-sans)",
              textDecoration: "none",
            }}
          >
            {showFullResult ? "Hide full result" : "View full result"}
          </button>

          {showFullResult && (
            <pre
              style={{
                marginTop: 8,
                padding: 12,
                borderRadius: "var(--wjn-radius-md)",
                background: "var(--wjn-surface-subtle)",
                border: "1px solid var(--wjn-line)",
                fontSize: 11.5,
                fontFamily: "var(--wjn-font-mono)",
                color: "var(--wjn-text-secondary)",
                maxHeight: 300,
                overflow: "auto",
                lineHeight: 1.5,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {JSON.stringify(result, null, 2)}
            </pre>
          )}
        </>
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
