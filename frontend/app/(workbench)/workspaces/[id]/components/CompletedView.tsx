"use client";

import { useState } from "react";

type TaskReportLike = {
  narrative?: unknown;
  result_summary?: unknown;
  outputs?: unknown;
  errors?: unknown;
};

export interface CompletedViewProps {
  resultSummary?: string | null;
  result?: Record<string, unknown> | null;
}

export function CompletedView({
  resultSummary,
  result,
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
