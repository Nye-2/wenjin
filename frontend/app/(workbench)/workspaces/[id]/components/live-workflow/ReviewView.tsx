"use client";

import type { WorkspacePrismReviewItem } from "@/lib/api/types";
import type { RunViewChangeSet } from "@/lib/change-set-view";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";

import {
  ChangeSetReviewPanel,
  type ChangeSetReviewActionState,
} from "../review-changes/ChangeSetReviewPanel";
import { ResultPreviewDetail } from "../result-preview/ResultPreviewDetail";
import { ResultPreviewList } from "../result-preview/ResultPreviewList";
import { EmptyState, GuidanceNote } from "./shared";
import { styles } from "./styles";
import { WritebackStatus, type RunWritebackStatus } from "./RunView";

export function ReviewView({
  previews,
  reviewItems,
  pendingReviewCount,
  changeSet,
  changeSetActionState,
  selectedPreviewId,
  writeback,
  onAcceptChangeUnits,
  onRejectChangeUnits,
  onUndoChangeUnits,
  onSelectPreview,
}: {
  previews: WorkspaceResultPreview[];
  reviewItems: WorkspacePrismReviewItem[];
  pendingReviewCount: number;
  changeSet: RunViewChangeSet | null;
  changeSetActionState?: ChangeSetReviewActionState;
  selectedPreviewId: string | null;
  writeback?: RunWritebackStatus;
  onAcceptChangeUnits: (unitIds: string[]) => void;
  onRejectChangeUnits: (unitIds: string[]) => void;
  onUndoChangeUnits: (unitIds: string[]) => void;
  onSelectPreview: (id: string) => void;
}) {
  if (changeSet) {
    return (
      <ChangeSetReviewPanel
        changeSet={changeSet}
        pendingReviewCount={pendingReviewCount}
        actionState={changeSetActionState}
        writeback={writeback}
        onAcceptUnits={onAcceptChangeUnits}
        onRejectUnits={onRejectChangeUnits}
        onUndoUnits={onUndoChangeUnits}
      />
    );
  }

  const selectedPreview =
    previews.find((preview) => preview.id === selectedPreviewId) ??
    previews[0] ??
    null;
  const hasReviewContent = previews.length > 0 || reviewItems.length > 0;
  const pendingCount = pendingReviewCount;

  if (!hasReviewContent) {
    return (
      <EmptyState
        title="暂无需要复核的变更"
        detail="运行结果和复核包会先出现在这里，复核确认后再保存到工作区房间。"
      />
    );
  }

  return (
    <div style={styles.reviewGrid}>
      <section style={styles.reviewInbox} aria-label="复核队列">
        <div style={styles.sectionHeaderCompact}>
          <div>
            <h2 style={{ ...styles.sectionTitle, margin: 0 }}>复核与保存</h2>
            <div style={styles.sectionSubtitle}>
              {pendingCount} 项内容待复核。
            </div>
          </div>
        </div>
        <GuidanceNote>
          先检查暂存结果，再保存确认过的工作区内容。
        </GuidanceNote>
        <div style={{ height: 12 }} />
        {previews.length > 0 ? (
          <ResultPreviewList
            previews={previews}
            selectedId={selectedPreview?.id ?? null}
            onSelect={onSelectPreview}
          />
        ) : (
          <EmptyState
            title="复核包待处理"
            detail="本次运行包含复核项，但暂时没有可直接预览的内容。"
            compact
          />
        )}
      </section>

      <aside style={styles.reviewDetail}>
        <ResultPreviewDetail
          preview={selectedPreview}
          footer={writeback ? <WritebackStatus writeback={writeback} /> : null}
        />
      </aside>
    </div>
  );
}
