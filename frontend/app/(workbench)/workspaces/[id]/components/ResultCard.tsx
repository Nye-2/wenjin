"use client";

import { useMemo, useState } from "react";

import {
  buildCommittedRoomLinks,
  commitExecutionOutputs,
  commitStateFromCommitResponse,
  commitStateRoomTargets,
  isExecutionCommitted,
  isExecutionDiscarded,
  readCommitStateFromResult,
  type ExecutionCommitRequest,
  type ExecutionCommitState,
} from "@/lib/execution-commit";
import { safeRuntimeText } from "@/lib/runtime-payload-safety";
import { groupWorkspaceResultPreviews } from "@/lib/workspace-result-kind";
import { buildWorkspaceResultPreviewsFromOutputs } from "@/lib/workspace-result-preview";
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

function isPrismReviewItem(item: WorkspacePrismReviewItem): boolean {
  return item.kind === "prism_file_change" || item.target?.kind === "prism_file_change";
}

function reviewNotice(items: WorkspacePrismReviewItem[]): string {
  const prismCount = items.filter(isPrismReviewItem).length;
  const artifactCount = items.filter((item) => item.kind === "sandbox_artifact").length;
  if (prismCount === items.length) {
    return `Prism 有 ${items.length} 项待确认修改`;
  }
  if (artifactCount === items.length) {
    return `产物有 ${items.length} 项待确认保存`;
  }
  return `有 ${items.length} 项待确认`;
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
    () =>
      canSaveAll
        ? outputs
        : outputs.map((output) => ({
            ...output,
            default_checked: false,
          })),
    [canSaveAll, outputs],
  );

  const previews = useMemo(
    () => buildWorkspaceResultPreviewsFromOutputs(safeOutputs),
    [safeOutputs],
  );
  const previewGroups = useMemo(
    () => groupWorkspaceResultPreviews(previews),
    [previews],
  );
  const representativePreviews = useMemo(() => previews.slice(0, 3), [previews]);
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
  const upsertExecution = useExecutionStore((state) => state.upsertExecution);
  const [idempotencyKey] = useState(() => generateUUID());
  const [localCommitState, setLocalCommitState] =
    useState<ExecutionCommitState | null>(null);
  const [committing, setCommitting] = useState(false);
  const [commitError, setCommitError] = useState<string | null>(null);
  const durableCommitState = readCommitStateFromResult(executionResult);
  const dataCommitState = readCommitStateFromResult(data);
  const effectiveCommitState =
    durableCommitState ?? dataCommitState ?? localCommitState;
  const committed = isExecutionCommitted(effectiveCommitState);
  const discarded = isExecutionDiscarded(effectiveCommitState);
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

  async function commit(body: ExecutionCommitRequest) {
    if (commitFinal || committing) {
      return;
    }
    setCommitError(null);
    setCommitting(true);
    try {
      const response = await commitExecutionOutputs({
        executionId: execution_id,
        idempotencyKey,
        body,
      });
      const outputIds = previews.map((preview) => preview.id);
      const acceptedIds = body.accept_all
        ? outputIds
        : (body.accepted_ids ?? []).filter((id) => outputIds.includes(id));
      const nextCommitState = commitStateFromCommitResponse(response, {
        acceptedIds,
        outputIds,
        discarded: !body.accept_all && acceptedIds.length === 0,
      });
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
          : "保存失败，请稍后重试",
      );
    } finally {
      setCommitting(false);
    }
  }

  function openReviewSurface() {
    selectRun(execution_id);
    const previewItemId = data.previewItemId ?? data.preview_item_id ?? null;
    if (previewItemId) {
      focusPreviewItem(previewItemId);
      setActiveWorkbenchTab("run");
    } else {
      focusPreviewItem(null);
      setActiveWorkbenchTab("review");
    }
    setWorkbenchFullscreen(true);
  }

  const statusLabel =
    status === "completed" ? "完成" : status === "failed_partial" ? "部分完成" : "已取消";
  const statusIconColor =
    status === "completed"
      ? "var(--wjn-success)"
      : status === "failed_partial"
        ? "var(--wjn-warning)"
        : "var(--wjn-error)";

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <span style={{ ...styles.statusIcon, color: statusIconColor }}>
          {status === "completed" ? "✓" : status === "failed_partial" ? "!" : "×"}
        </span>
        <span style={styles.headerTitle}>
          {capability_name ?? "Execution"} {statusLabel}
        </span>
        {duration_seconds != null ? (
          <span style={styles.duration}>{duration_seconds}s</span>
        ) : null}
      </div>

      {narrativeText ? <div style={styles.narrative}>{narrativeText}</div> : null}
      {!canSaveAll && previews.length > 0 ? (
        <div style={styles.partialNotice}>
          本次运行未完整完成，候选结果需要先查看详情后再决定是否保存。
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
              预览待确认修改
            </WorkspaceActionLink>
          ) : null}
        </div>
      ) : null}

      {previews.length > 0 ? (
        <div style={styles.packageShell}>
          <div style={styles.packageHeader}>
            <div style={styles.receiptMeta}>
              <span>{previews.length} 项结果待处理</span>
            </div>
            <div style={styles.groupStats}>
              {previewGroups.map((group) => (
                <span
                  key={group.kind}
                  style={{
                    ...styles.groupStat,
                    color: group.meta.accent,
                    background: group.meta.tint,
                    borderColor: group.meta.border,
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
                        borderColor: groupMeta?.border ?? "rgba(20,20,30,0.1)",
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
            {canSaveAll ? (
              <button
                type="button"
                onClick={() => commit({ accept_all: true })}
                disabled={commitFinal || committing}
                style={{
                  ...styles.primaryButton,
                  ...(commitFinal || committing ? styles.buttonDisabled : null),
                }}
              >
                {committed
                  ? "已保存到工作区"
                  : discarded
                    ? "已暂不保存"
                    : committing
                      ? "保存中..."
                      : "保存到工作区"}
              </button>
            ) : (
              <button
                type="button"
                onClick={openReviewSurface}
                style={styles.primaryButton}
              >
                查看候选项
              </button>
            )}
            {canSaveAll ? (
              <button
                type="button"
                onClick={openReviewSurface}
                style={styles.secondaryButton}
              >
                查看详情
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => commit({ accepted_ids: [] })}
              disabled={commitFinal || committing}
              style={{
                ...styles.ghostButton,
                ...(commitFinal || committing ? styles.buttonDisabled : null),
              }}
            >
              {discarded ? "已暂不保存" : "暂不保存"}
            </button>
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
    background: "var(--wjn-surface-raised)",
    backdropFilter: "blur(12px)",
    WebkitBackdropFilter: "blur(12px)",
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
    background: "rgba(198, 138, 26, 0.08)",
    border: "1px solid rgba(198, 138, 26, 0.16)",
    color: "var(--wjn-warning)",
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
    background: "rgba(255,255,255,0.62)",
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
  ghostButton: {
    border: "1px solid rgba(20, 20, 30, 0.08)",
    background: "rgba(255, 255, 255, 0.72)",
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
    borderRadius: "var(--wjn-radius-sm)",
    border: "1px solid rgba(20,20,30,0.08)",
    background: "rgba(255,255,255,0.72)",
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
