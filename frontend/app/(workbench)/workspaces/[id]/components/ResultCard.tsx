"use client";

import { useEffect, useMemo, useState } from "react";

import {
  buildCommittedRoomLinks,
  commitExecutionOutputs,
  type CommittedRoomLink,
} from "@/lib/execution-commit";
import { buildWorkspaceResultPreviewsFromOutputs } from "@/lib/workspace-result-preview";
import { PrismReviewList } from "@/components/prism/PrismReviewList";
import type { ResultCardData } from "@/stores/chat-store";
import { CommitActionBar } from "./result-preview/CommitActionBar";
import { ResultPreviewDetail } from "./result-preview/ResultPreviewDetail";
import { WorkspaceActionLink } from "./WorkspaceActionLink";

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

  const previews = useMemo(
    () => buildWorkspaceResultPreviewsFromOutputs(outputs),
    [outputs],
  );
  const [expanded, setExpanded] = useState(false);
  const [selectedPreviewId, setSelectedPreviewId] = useState<string | null>(null);
  const [idempotencyKey] = useState(() => generateUUID());
  const [checkedIds, setCheckedIds] = useState<Set<string>>(() => {
    const ids = new Set<string>();
    for (const preview of previews) {
      if (preview.defaultChecked) {
        ids.add(preview.id);
      }
    }
    return ids;
  });
  const [committed, setCommitted] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [commitLinks, setCommitLinks] = useState<CommittedRoomLink[]>([]);
  const [commitError, setCommitError] = useState<string | null>(null);

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

  function toggleChecked(id: string) {
    setCheckedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  async function commit(body: object) {
    if (committed || committing) {
      return;
    }
    setCommitError(null);
    setCommitting(true);
    try {
      const response = await commitExecutionOutputs({
        executionId: execution_id,
        idempotencyKey,
        body: body as Record<string, unknown>,
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

  const statusLabel =
    status === "completed" ? "完成" : status === "failed_partial" ? "部分完成" : "已取消";

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <span style={styles.statusIcon}>
          {status === "completed" ? "✓" : status === "failed_partial" ? "!" : "×"}
        </span>
        <span style={styles.headerTitle}>
          {capability_name ?? "Execution"} {statusLabel}
        </span>
        {duration_seconds != null ? (
          <span style={styles.duration}>{duration_seconds}s</span>
        ) : null}
      </div>

      {narrative ? <div style={styles.narrative}>{narrative}</div> : null}

      {data.review_items?.length ? (
        <div style={styles.reviewItems}>
          <PrismReviewList items={data.review_items} />
          {workspaceId ? (
            <WorkspaceActionLink
              href={`/workspaces/${workspaceId}/prism?focus=file_changes`}
              style={styles.savedLink}
            >
              预览待确认修改
            </WorkspaceActionLink>
          ) : null}
        </div>
      ) : null}

      <div style={styles.receiptRow}>
        <div style={styles.receiptMeta}>
          <span>{previews.length} 项结果待处理</span>
        </div>
        {previews.length > 0 ? (
          <button
            type="button"
            onClick={() => setExpanded((prev) => !prev)}
            style={styles.toggleButton}
          >
            {expanded ? "收起结果" : "查看结果"}
          </button>
        ) : null}
      </div>

      {expanded ? (
        <div style={styles.expandedShell}>
          <div style={styles.previewList}>
            {previews.map((preview) => {
              const isSelected = preview.id === selectedPreview?.id;
              return (
                <label
                  key={preview.id}
                  style={{
                    ...styles.previewRow,
                    ...(isSelected ? styles.previewRowSelected : {}),
                  }}
                >
                  <input
                    type="checkbox"
                    checked={checkedIds.has(preview.id)}
                    onChange={() => toggleChecked(preview.id)}
                    onClick={(event) => event.stopPropagation()}
                    disabled={committed}
                    style={styles.checkbox}
                  />
                  <button
                    type="button"
                    onClick={() => setSelectedPreviewId(preview.id)}
                    style={styles.previewSelectButton}
                  >
                    <div style={styles.previewTitle}>{preview.title}</div>
                    {preview.subtitle ? (
                      <div style={styles.previewSubtitle}>{preview.subtitle}</div>
                    ) : null}
                    {preview.previewText ? (
                      <div style={styles.previewSnippet}>
                        {summarize(preview.previewText)}
                      </div>
                    ) : null}
                  </button>
                </label>
              );
            })}
          </div>

          <ResultPreviewDetail preview={selectedPreview} />

          <div style={styles.commitBar}>
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

function summarize(value: string): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= 92) {
    return normalized;
  }
  return `${normalized.slice(0, 89)}...`;
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    padding: "var(--v2-space-5)",
    background: "var(--v2-glass-bg)",
    backdropFilter: "var(--v2-glass-blur)",
    WebkitBackdropFilter: "var(--v2-glass-blur)",
    borderRadius: "var(--v2-radius-lg)",
    border: "1px solid var(--v2-glass-border)",
    boxShadow: "var(--v2-glass-shadow)",
    margin: "var(--v2-space-2) 0",
    fontFamily: "var(--v2-font-sans)",
    fontSize: 13,
    color: "var(--v2-text-primary)",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    marginBottom: 4,
    fontWeight: 500,
  },
  statusIcon: {
    color: "var(--v2-status-success-deep)",
    fontSize: 14,
  },
  headerTitle: {
    fontVariantNumeric: "tabular-nums",
  },
  duration: {
    marginLeft: "auto",
    fontSize: 12,
    color: "var(--v2-text-tertiary)",
    fontVariantNumeric: "tabular-nums",
  },
  narrative: {
    color: "var(--v2-text-secondary)",
    fontSize: 12.5,
    marginBottom: "var(--v2-space-3)",
    lineHeight: 1.5,
  },
  reviewItems: {
    display: "grid",
    gap: 8,
    marginBottom: "var(--v2-space-3)",
  },
  receiptRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  receiptMeta: {
    fontSize: 12,
    color: "var(--v2-text-tertiary)",
  },
  toggleButton: {
    border: "1px solid rgba(124, 58, 237, 0.18)",
    background: "rgba(124, 58, 237, 0.08)",
    color: "var(--v2-accent-purple-700)",
    borderRadius: "var(--v2-radius-pill)",
    padding: "6px 12px",
    fontSize: 12.5,
    fontWeight: 600,
    cursor: "pointer",
  },
  expandedShell: {
    marginTop: "var(--v2-space-4)",
    display: "grid",
    gap: 12,
  },
  previewList: {
    display: "grid",
    gap: 8,
  },
  previewRow: {
    display: "flex",
    alignItems: "flex-start",
    gap: 10,
    padding: "10px 12px",
    borderRadius: "var(--v2-radius-md)",
    border: "1px solid rgba(20, 20, 30, 0.08)",
    background: "rgba(255, 255, 255, 0.72)",
  },
  previewRowSelected: {
    border: "1px solid rgba(124, 58, 237, 0.24)",
    background: "rgba(124, 58, 237, 0.06)",
    boxShadow: "0 0 0 3px rgba(124, 58, 237, 0.08)",
  },
  checkbox: {
    marginTop: 3,
    accentColor: "var(--v2-accent-purple-700)",
    cursor: "pointer",
  },
  previewSelectButton: {
    flex: 1,
    border: "none",
    background: "transparent",
    padding: 0,
    textAlign: "left",
    cursor: "pointer",
  },
  previewTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: "var(--v2-text-primary)",
    marginBottom: 4,
  },
  previewSubtitle: {
    fontSize: 12,
    color: "var(--v2-text-tertiary)",
    marginBottom: 4,
  },
  previewSnippet: {
    fontSize: 12.5,
    lineHeight: 1.5,
    color: "var(--v2-text-secondary)",
  },
  commitBar: {
    paddingTop: 2,
  },
  commitError: {
    padding: "8px 10px",
    borderRadius: "var(--v2-radius-md)",
    background: "rgba(220, 38, 38, 0.06)",
    border: "1px solid rgba(220, 38, 38, 0.12)",
    color: "var(--v2-status-error)",
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
    borderRadius: "var(--v2-radius-pill)",
    background: "rgba(59, 130, 246, 0.08)",
    border: "1px solid rgba(59, 130, 246, 0.16)",
    color: "var(--v2-accent-blue-700)",
    fontSize: 12.5,
    fontWeight: 500,
    textDecoration: "none",
  },
};
