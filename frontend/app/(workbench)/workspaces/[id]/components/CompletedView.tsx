"use client";

import { useEffect, useMemo, useState } from "react";
import { resolveExecutionNextActionPresentation } from "@/lib/block-actions";
import {
  buildCommittedRoomLinks,
  commitExecutionOutputs,
  type CommittedRoomLink,
} from "@/lib/execution-commit";
import { buildWorkspaceResultPreviewsFromOutputs } from "@/lib/workspace-result-preview";
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
};

export interface CompletedViewProps {
  workspaceId?: string | null;
  featureId?: string | null;
  executionId?: string | null;
  resultSummary?: string | null;
  result?: Record<string, unknown> | null;
  nextActions?: Array<Record<string, unknown>>;
}

export function CompletedView({
  workspaceId,
  featureId,
  executionId,
  resultSummary,
  result,
  nextActions = [],
}: CompletedViewProps) {
  const [showFullResult, setShowFullResult] = useState(false);
  const [idempotencyKey] = useState(() => generateUUID());

  const taskReport = getTaskReport(result);
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
    result,
    taskReport,
    nextActions,
  });

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
        fontFamily: "var(--v2-font-sans)",
        color: "var(--v2-text-primary)",
      }}
    >
      {/* Summary text */}
      <div
        style={{
          fontSize: 13,
          lineHeight: 1.5,
          color: "var(--v2-text-secondary)",
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
              actionContext.fileChanges.length > 0 ? (
                <div
                  style={{
                    paddingTop: 12,
                    borderTop: "1px solid rgba(20, 20, 30, 0.08)",
                  }}
                >
                  {executionId ? (
                    <div style={{ marginBottom: 12 }}>
                      <div
                        style={{
                          fontSize: 12,
                          fontWeight: 600,
                          color: "var(--v2-text-primary)",
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

                  {(actionContext.fileChanges.length > 0 ||
                    actionContext.actions.length > 0) && (
                    <div
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        color: "var(--v2-text-primary)",
                        marginBottom: actionContext.fileChanges.length > 0 ? 8 : 6,
                      }}
                    >
                      {actionContext.fileChanges.length > 0
                        ? "待确认修改"
                        : "下一步操作"}
                    </div>
                  )}

                  {actionContext.fileChanges.length > 0 && (
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: 6,
                        marginBottom: actionContext.actions.length > 0 ? 10 : 0,
                      }}
                    >
                      {actionContext.fileChanges.map((change) => (
                        <div
                          key={change.key}
                          style={{
                            display: "flex",
                            flexWrap: "wrap",
                            alignItems: "center",
                            gap: 6,
                            fontSize: 11.5,
                            lineHeight: 1.45,
                            color: "var(--v2-text-secondary)",
                          }}
                        >
                          <span style={{ color: "var(--v2-text-primary)", fontWeight: 500 }}>
                            {change.path}
                          </span>
                          {change.reason ? (
                            <span style={{ color: "var(--v2-text-tertiary)" }}>
                              {change.reason}
                            </span>
                          ) : null}
                        </div>
                      ))}
                    </div>
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
                  borderRadius: "var(--v2-radius-md)",
                  background: "rgba(220, 38, 38, 0.06)",
                  border: "1px solid rgba(220, 38, 38, 0.12)",
                  color: "var(--v2-status-error)",
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
        (actionContext.actions.length > 0 || actionContext.fileChanges.length > 0) && (
        <div
          style={{
            marginBottom: 12,
            padding: "10px 12px",
            borderRadius: "var(--v2-radius-md)",
            background: "rgba(124, 58, 237, 0.06)",
            border: "1px solid rgba(124, 58, 237, 0.12)",
          }}
        >
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "var(--v2-text-primary)",
              marginBottom: actionContext.fileChanges.length > 0 ? 8 : 0,
            }}
          >
            {actionContext.fileChanges.length > 0 ? "待确认修改" : "下一步操作"}
          </div>

          {actionContext.fileChanges.length > 0 && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 6,
                marginBottom: actionContext.actions.length > 0 ? 10 : 0,
              }}
            >
              {actionContext.fileChanges.map((change) => (
                <div
                  key={change.key}
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "center",
                    gap: 6,
                    fontSize: 11.5,
                    lineHeight: 1.45,
                    color: "var(--v2-text-secondary)",
                  }}
                >
                  <span style={{ color: "var(--v2-text-primary)", fontWeight: 500 }}>
                    {change.path}
                  </span>
                  {change.reason ? (
                    <span style={{ color: "var(--v2-text-tertiary)" }}>
                      {change.reason}
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
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
              color: "var(--v2-accent-purple-700)",
              fontSize: 12,
              fontWeight: 500,
              cursor: "pointer",
              fontFamily: "var(--v2-font-sans)",
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
                borderRadius: "var(--v2-radius-md)",
                background: "var(--v2-surface-card)",
                border: "1px solid var(--v2-border-soft)",
                fontSize: 11.5,
                fontFamily: "var(--v2-font-mono)",
                color: "var(--v2-text-secondary)",
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

type PrismReviewAction = {
  key: string;
  label: string;
  href: string | null;
};

type PrismFileChange = {
  key: string;
  path: string;
  reason: string | null;
};

function getCompletedActionContext(options: {
  workspaceId?: string | null;
  featureId?: string | null;
  executionId?: string | null;
  result: Record<string, unknown> | null | undefined;
  taskReport: TaskReportLike | null;
  nextActions: Array<Record<string, unknown>>;
}): {
  actions: PrismReviewAction[];
  fileChanges: PrismFileChange[];
} {
  const {
    workspaceId,
    featureId,
    executionId,
    result,
    taskReport,
    nextActions,
  } = options;
  const data = readObject(taskReport?.data) ?? readObject(result?.data);
  const rawFileChanges = Array.isArray(data?.file_changes) ? data.file_changes : [];
  const fileChanges = rawFileChanges
    .map((item, index) => {
      const change = readObject(item);
      if (!change) {
        return null;
      }
      const path =
        readString(change.path) ??
        readString(change.section_file) ??
        readString(change.logical_key);
      if (!path) {
        return null;
      }
      return {
        key: readString(change.logical_key) ?? `${path}:${index}`,
        path,
        reason: readString(change.reason),
      };
    })
    .filter((item): item is PrismFileChange => item !== null);

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

  return { actions, fileChanges };
}

function readObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

const styles: Record<string, React.CSSProperties> = {
  commitError: {
    marginTop: 10,
    padding: "8px 10px",
    borderRadius: "var(--v2-radius-md)",
    background: "rgba(220, 38, 38, 0.06)",
    border: "1px solid rgba(220, 38, 38, 0.12)",
    color: "var(--v2-status-error)",
    fontSize: 11.5,
    lineHeight: 1.45,
  },
  reviewActionLink: {
    display: "inline-flex",
    alignItems: "center",
    padding: "4px 10px",
    borderRadius: "var(--v2-radius-pill)",
    background: "var(--v2-accent-purple-100)",
    color: "var(--v2-accent-purple-700)",
    fontSize: 11.5,
    fontWeight: 500,
    lineHeight: "18px",
    textDecoration: "none",
  },
  reviewActionBadge: {
    display: "inline-flex",
    alignItems: "center",
    padding: "4px 10px",
    borderRadius: "var(--v2-radius-pill)",
    background: "rgba(20, 20, 30, 0.06)",
    color: "var(--v2-text-secondary)",
    fontSize: 11.5,
    fontWeight: 500,
    lineHeight: "18px",
  },
};
