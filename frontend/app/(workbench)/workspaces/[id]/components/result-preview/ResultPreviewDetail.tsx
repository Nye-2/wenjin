"use client";

import type { ReactNode } from "react";

import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";
import { ResultPreviewRenderer } from "./ResultPreviewRenderer";

interface ResultPreviewDetailProps {
  preview: WorkspaceResultPreview | null;
  footer?: ReactNode;
}

export function ResultPreviewDetail({
  preview,
  footer,
}: ResultPreviewDetailProps) {
  if (!preview) {
    return (
      <div
        style={{
          padding: "16px",
          borderRadius: "var(--v2-radius-lg)",
          border: "1px solid rgba(20, 20, 30, 0.08)",
          background: "rgba(255, 255, 255, 0.72)",
          color: "var(--v2-text-tertiary)",
          fontSize: 13,
        }}
      >
        Select a result to preview it here.
      </div>
    );
  }

  return (
    <div
      style={{
        padding: "16px",
        borderRadius: "var(--v2-radius-lg)",
        border: "1px solid rgba(20, 20, 30, 0.08)",
        background: "rgba(255, 255, 255, 0.84)",
        boxShadow: "0 12px 28px rgba(20, 20, 30, 0.05)",
      }}
    >
      {preview.badge ? (
        <div
          style={{
            marginBottom: 8,
            fontSize: 11.5,
            fontWeight: 600,
            color: "var(--v2-accent-purple-700)",
            textTransform: "uppercase",
          }}
        >
          {preview.badge}
        </div>
      ) : null}
      <div
        style={{
          fontSize: 16,
          lineHeight: 1.4,
          fontWeight: 650,
          color: "var(--v2-text-primary)",
          marginBottom: preview.subtitle ? 4 : 10,
        }}
      >
        {preview.title}
      </div>
      {preview.subtitle ? (
        <div
          style={{
            fontSize: 13,
            color: "var(--v2-text-tertiary)",
            marginBottom: 10,
          }}
        >
          {preview.subtitle}
        </div>
      ) : null}
      {preview.metadataLines.length > 0 ? (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            marginBottom: 12,
          }}
        >
          {preview.metadataLines.map((line) => (
            <span
              key={line}
              style={{
                padding: "2px 8px",
                borderRadius: "var(--v2-radius-pill)",
                background: "rgba(20, 20, 30, 0.06)",
                color: "var(--v2-text-secondary)",
                fontSize: 11.5,
              }}
            >
              {line}
            </span>
          ))}
        </div>
      ) : null}
      <ResultPreviewRenderer preview={preview} />
      {footer ? (
        <div style={{ marginTop: 14 }}>
          {footer}
        </div>
      ) : null}
    </div>
  );
}
