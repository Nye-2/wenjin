"use client";

import { useState } from "react";

export interface CompletedViewProps {
  resultSummary?: string | null;
  result?: Record<string, unknown> | null;
  outputs?: unknown[];
}

export function CompletedView({
  resultSummary,
  result,
  outputs,
}: CompletedViewProps) {
  const [showFullResult, setShowFullResult] = useState(false);

  const summary = resultSummary || "Execution completed.";
  const outputItems = Array.isArray(outputs) ? outputs.slice(0, 5) : [];

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
              (item.title as string) ||
              (item.name as string) ||
              (item.id as string) ||
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
