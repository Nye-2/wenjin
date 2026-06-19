import { useMemo, useState } from "react";
import { Edit3, ExternalLink, FileText } from "lucide-react";

import type {
  ExecutionRecord,
  WorkspacePrismReviewItem,
} from "@/lib/api/types";
import type { CommittedRoomLink } from "@/lib/execution-commit";
import {
  groupWorkspaceResultPreviews,
} from "@/lib/workspace-result-kind";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";
import type { WorkbenchDraftEdit } from "@/stores/workbench-layout-store";

import { CommitActionBar } from "../result-preview/CommitActionBar";
import { ResultPreviewDetail } from "../result-preview/ResultPreviewDetail";
import { WorkspaceActionLink } from "../WorkspaceActionLink";
import { ResultEditor } from "./ResultEditor";
import { EmptyState, GuidanceNote, ResultKindBadge } from "./shared";
import { styles } from "./styles";

export function ReviewView({
  workspaceId,
  record,
  previews,
  selectedPreview,
  selectedDraft,
  draftEdits,
  checkedIds,
  committed,
  committing,
  commitLinks,
  commitError,
  reviewItems,
  isFullscreen,
  onSelectPreview,
  onEnterDetailMode,
  onToggleChecked,
  onPatchDraft,
  onSetDraft,
  onAcceptAll,
  onAcceptSelected,
  onDiscard,
}: {
  workspaceId: string;
  record: ExecutionRecord | null;
  previews: WorkspaceResultPreview[];
  selectedPreview: WorkspaceResultPreview | null;
  selectedDraft?: WorkbenchDraftEdit;
  draftEdits: Record<string, WorkbenchDraftEdit>;
  checkedIds: Set<string>;
  committed: boolean;
  committing: boolean;
  commitLinks: CommittedRoomLink[];
  commitError: string | null;
  reviewItems: WorkspacePrismReviewItem[];
  isFullscreen: boolean;
  onSelectPreview: (id: string) => void;
  onEnterDetailMode: () => void;
  onToggleChecked: (id: string) => void;
  onPatchDraft: (outputId: string, field: string, value: unknown) => void;
  onSetDraft: (outputId: string, edit: WorkbenchDraftEdit | null) => void;
  onAcceptAll: () => void;
  onAcceptSelected: () => void;
  onDiscard: () => void;
}) {
  const previewGroups = useMemo(
    () => groupWorkspaceResultPreviews(previews),
    [previews],
  );
  const [activeKind, setActiveKind] = useState<string>("all");
  const effectiveKind =
    activeKind === "all" || previewGroups.some((group) => group.kind === activeKind)
      ? activeKind
      : "all";
  const visibleGroups = useMemo(() => {
    return effectiveKind === "all"
      ? previewGroups
      : previewGroups.filter((group) => group.kind === effectiveKind);
  }, [effectiveKind, previewGroups]);
  const committablePreviews = previews.filter((preview) => preview.canCommit);
  const committableIds = new Set(committablePreviews.map((preview) => preview.id));
  const selectedCommitCount = Array.from(checkedIds).filter((id) =>
    committableIds.has(id),
  ).length;
  const allowAcceptAll = record?.status === "completed" && committablePreviews.length > 0;
  const prismReviewItems = reviewItems.filter(
    (item) => item.kind !== "sandbox_artifact" && item.target?.kind !== "sandbox_artifact",
  );

  function activateFilter(kind: string) {
    setActiveKind(kind);
    if (kind === "all") {
      return;
    }
    const firstItem = previewGroups.find((group) => group.kind === kind)?.items[0];
    if (firstItem && firstItem.id !== selectedPreview?.id) {
      onSelectPreview(firstItem.id);
    }
  }

  function activatePreview(previewId: string) {
    onSelectPreview(previewId);
    if (!isFullscreen) {
      onEnterDetailMode();
    }
  }

  if (!record) {
    return <EmptyState title="暂无待确认结果" detail="完成运行后，候选文档、文献、记忆、决策和任务会进入这里。" />;
  }

  return (
    <div
      style={{
        ...styles.reviewGrid,
        ...(!isFullscreen ? styles.reviewGridSingle : null),
      }}
    >
      <section
        role="region"
        aria-label="候选结果列表"
        style={styles.reviewInbox}
      >
        <div style={styles.sectionHeader}>
          <div>
            <div style={styles.sectionTitle}>候选结果</div>
            <div style={styles.sectionSubtitle}>按类型筛选，点选后在右侧查看详情。</div>
          </div>
          <span style={styles.countBadge}>{previews.length} 项</span>
        </div>
        <div style={styles.reviewFilterBar} aria-label="候选结果筛选">
          <button
            type="button"
            aria-label="筛选全部结果"
            title="全部"
            onClick={() => activateFilter("all")}
            style={{
              ...styles.reviewFilterButton,
              ...(effectiveKind === "all" ? styles.reviewFilterButtonActive : null),
            }}
          >
            全部
            <span style={styles.filterCount}>{previews.length}</span>
          </button>
          {previewGroups.map((group) => (
            <button
              key={group.kind}
              type="button"
              aria-label={`筛选${group.meta.groupLabel}`}
              title={group.meta.groupLabel}
              onClick={() => activateFilter(group.kind)}
              style={{
                ...styles.reviewFilterButton,
                ...(effectiveKind === group.kind
                  ? {
                      ...styles.reviewFilterButtonActive,
                      color: group.meta.accent,
                      borderColor: group.meta.border,
                      background: group.meta.tint,
                    }
                  : null),
              }}
            >
              {group.meta.shortLabel}
              <span style={styles.filterCount}>{group.items.length}</span>
            </button>
          ))}
        </div>
        <div style={{ marginBottom: 12 }}>
          <GuidanceNote>
            候选结果不会自动写入工作区。先点开预览，勾选想保留的内容，再保存。
          </GuidanceNote>
        </div>
        {previews.length > 0 ? (
          <div style={styles.previewList}>
            {visibleGroups.map((group) => (
              <section key={group.kind} style={styles.previewGroupCompact}>
                <div style={styles.previewGroupHeader}>
                  <span
                    style={{
                      ...styles.previewGroupTitle,
                      color: group.meta.accent,
                    }}
                  >
                    {group.meta.groupLabel}
                  </span>
                  <span
                    style={{
                      ...styles.previewGroupCount,
                      background: group.meta.tint,
                      borderColor: group.meta.border,
                      color: group.meta.accent,
                    }}
                  >
                    {group.items.length}
                  </span>
                </div>
                <div style={styles.previewGroupList}>
                  {group.items.map((preview) => {
                    const selected = selectedPreview?.id === preview.id;
                    return (
                      <div
                        key={preview.id}
                        onClick={() => activatePreview(preview.id)}
                        style={{
                          ...styles.previewListItem,
                          ...(selected ? styles.previewListItemActive : null),
                          ...(selected
                            ? {
                                borderColor: group.meta.border,
                                background: group.meta.tint,
                              }
                            : null),
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={preview.canCommit && checkedIds.has(preview.id)}
                          disabled={committed || !preview.canCommit}
                          title={preview.canCommit ? "保存到工作区" : "该项由独立产物确认入口处理"}
                          onClick={(event) => event.stopPropagation()}
                          onChange={() => {
                            if (preview.canCommit) {
                              onToggleChecked(preview.id);
                            }
                          }}
                          style={styles.checkbox}
                        />
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            activatePreview(preview.id);
                          }}
                          style={styles.previewListButton}
                        >
                          <span style={styles.previewTitle}>{preview.title}</span>
                          <span style={styles.previewMeta}>
                            <ResultKindBadge kind={preview.kind} />
                            {preview.subtitle ? (
                              <span style={styles.previewSubtitleInline}>
                                {preview.subtitle}
                              </span>
                            ) : null}
                          </span>
                        </button>
                        {draftEdits[preview.id] ? (
                          <Edit3 size={13} color="var(--wjn-blue)" />
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        ) : (
          <EmptyState title="没有候选结果" detail="如果是 Prism 文件级修改，请从下方入口进入 Prism 精修。" compact />
        )}

        <div style={styles.commitBox}>
          {!allowAcceptAll && committablePreviews.length > 0 ? (
            <GuidanceNote tone="warning">
              本次运行未完整完成，默认不会全选候选项。请逐项预览后保存已勾选内容。
            </GuidanceNote>
          ) : null}
          {committablePreviews.length > 0 ? (
            <CommitActionBar
              committed={committed}
              committing={committing}
              allowAcceptAll={allowAcceptAll}
              selectedCount={selectedCommitCount}
              onAcceptAll={onAcceptAll}
              onAcceptSelected={onAcceptSelected}
              onDiscard={onDiscard}
              acceptAllLabel="全部保存"
              acceptSelectedLabel="保存已勾选"
              discardLabel="暂不保存"
              committedLabel="已写入工作区"
            />
          ) : previews.length > 0 ? (
            <div style={styles.reviewNotice}>
              这些候选来自沙盒产物，可先预览；保存或忽略会由产物确认入口处理。
            </div>
          ) : null}
          {commitError ? <div style={styles.commitError}>{commitError}</div> : null}
          {commitLinks.length > 0 ? (
            <div style={styles.linkWrap}>
              {commitLinks.map((link) => (
                <WorkspaceActionLink key={link.key} href={link.href} style={styles.roomLink}>
                  <ExternalLink size={12} />
                  {link.label}
                </WorkspaceActionLink>
              ))}
            </div>
          ) : null}
        </div>

        {prismReviewItems.length > 0 ? (
          <div style={styles.prismBox}>
            <div style={styles.sectionTitleSmall}>Prism 文件级修改</div>
            <div style={styles.sectionSubtitle}>精细 diff、patch 和保护区仍在 Prism 页面完成。</div>
            <div style={styles.linkWrap}>
              <WorkspaceActionLink href={`/workspaces/${workspaceId}/prism`} style={styles.roomLink}>
                <FileText size={12} />
                打开 Prism 确认
              </WorkspaceActionLink>
            </div>
          </div>
        ) : null}
      </section>

      {isFullscreen ? (
        <section
          role="region"
          aria-label="候选结果详情"
          style={styles.reviewDetail}
        >
          {selectedPreview ? (
            <>
              <ResultPreviewDetail preview={selectedPreview} />
              {selectedPreview.canCommit ? (
                <ResultEditor
                  preview={selectedPreview}
                  draft={selectedDraft}
                  disabled={committed}
                  onPatchDraft={onPatchDraft}
                  onSetDraft={onSetDraft}
                />
              ) : null}
            </>
          ) : (
            <EmptyState title="选择一个候选结果" detail="右侧会显示预览和可编辑字段。" compact />
          )}
        </section>
      ) : null}
    </div>
  );
}
