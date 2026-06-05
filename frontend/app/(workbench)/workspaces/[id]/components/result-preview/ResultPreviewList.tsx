"use client";

import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";

interface ResultPreviewListProps {
  previews: WorkspaceResultPreview[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  checkedIds?: Set<string>;
  onToggleChecked?: (id: string) => void;
  disabled?: boolean;
}

function summarizePreviewText(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= 84) {
    return normalized;
  }
  return `${normalized.slice(0, 81)}...`;
}

export function ResultPreviewList({
  previews,
  selectedId,
  onSelect,
  checkedIds,
  onToggleChecked,
  disabled = false,
}: ResultPreviewListProps) {
  return (
    <div
      style={{
        display: "grid",
        gap: 8,
      }}
    >
      {previews.map((preview) => {
        const isSelected = preview.id === selectedId;
        return (
          <div
            key={preview.id}
            data-testid="result-preview-item"
            data-selected={isSelected ? "true" : "false"}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              width: "100%",
              textAlign: "left",
              padding: "10px 12px",
              borderRadius: "var(--wjn-radius-md)",
              border: isSelected
                ? "1px solid var(--wjn-accent-line)"
                : "1px solid rgba(20, 20, 30, 0.08)",
              background: isSelected
                ? "var(--wjn-accent-soft)"
                : "rgba(255, 255, 255, 0.72)",
              boxShadow: isSelected
                ? "0 0 0 3px var(--wjn-accent-soft)"
                : "none",
            }}
          >
            {checkedIds && onToggleChecked ? (
              <input
                type="checkbox"
                checked={checkedIds.has(preview.id)}
                onChange={() => onToggleChecked(preview.id)}
                disabled={disabled}
                style={{
                  marginTop: 3,
                  accentColor: "var(--wjn-blue)",
                  cursor: disabled ? "not-allowed" : "pointer",
                }}
              />
            ) : null}
            <button
              type="button"
              onClick={() => onSelect(preview.id)}
              style={{
                flex: 1,
                border: "none",
                background: "transparent",
                padding: 0,
                textAlign: "left",
                cursor: "pointer",
              }}
            >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
                marginBottom: 4,
              }}
            >
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: "var(--wjn-text)",
                }}
              >
                {preview.title}
              </div>
              {preview.badge ? (
                <span
                  style={{
                    flexShrink: 0,
                    padding: "2px 8px",
                    borderRadius: "var(--wjn-radius-pill)",
                    background: "rgba(20, 20, 30, 0.06)",
                    color: "var(--wjn-text-secondary)",
                    fontSize: 11,
                    fontWeight: 500,
                  }}
                >
                  {preview.badge}
                </span>
              ) : null}
            </div>
            {preview.subtitle ? (
              <div
                style={{
                  fontSize: 12,
                  color: "var(--wjn-text-muted)",
                  marginBottom: 6,
                }}
              >
                {preview.subtitle}
              </div>
            ) : null}
            {summarizePreviewText(preview.previewText) ? (
              <div
                style={{
                  fontSize: 12.5,
                  lineHeight: 1.5,
                  color: "var(--wjn-text-secondary)",
                }}
              >
                {summarizePreviewText(preview.previewText)}
              </div>
            ) : null}
            </button>
          </div>
        );
      })}
    </div>
  );
}
