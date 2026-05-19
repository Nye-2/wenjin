"use client";

import { useState } from "react";
import { resolveExecutionNextActionPresentation } from "@/lib/block-actions";

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

  const taskReport = getTaskReport(result);
  const summary =
    resultSummary ||
    readString(taskReport?.result_summary) ||
    readString(taskReport?.narrative) ||
    "Execution completed.";
  const taskOutputs = taskReport?.outputs;
  const outputItems = Array.isArray(taskOutputs) ? taskOutputs.slice(0, 5) : [];
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
          marginBottom: outputItems.length > 0 ? 12 : 8,
        }}
      >
        {summary}
      </div>

      {/* Output pills */}
      {outputItems.length > 0 && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 6,
            marginBottom: 12,
          }}
        >
          {outputItems.map((output, i) => {
            const item = output as Record<string, unknown>;
            const label =
              readString(item.preview) ||
              readString(item.title) ||
              readString(item.name) ||
              readString((item.data as Record<string, unknown> | undefined)?.title) ||
              readString((item.data as Record<string, unknown> | undefined)?.name) ||
              readString(item.id) ||
              `Output ${i + 1}`;
            return (
              <span
                key={i}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  padding: "3px 10px",
                  borderRadius: "var(--v2-radius-pill)",
                  background: "var(--v2-accent-purple-100)",
                  color: "var(--v2-accent-purple-700)",
                  fontSize: 11,
                  fontWeight: 500,
                  lineHeight: "18px",
                }}
              >
                {label}
              </span>
            );
          })}
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

      {(actionContext.actions.length > 0 || actionContext.fileChanges.length > 0) && (
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
                  <a
                    key={action.key}
                    href={action.href}
                    style={styles.reviewActionLink}
                  >
                    {action.label}
                  </a>
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
      {result && (
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
  const resultProjectId =
    readString(data?.latex_project_id) ?? readString(data?.project_id);
  const resultPrismUrl = readString(data?.prism_url);
  const prismHref = resultPrismUrl || (resultProjectId ? `/latex/${resultProjectId}` : null);

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
        prismHref,
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
