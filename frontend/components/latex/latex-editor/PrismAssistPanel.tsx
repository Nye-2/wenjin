"use client";

import type {
  CSSProperties,
  PointerEvent,
  RefObject,
} from "react";
import {
  useRef,
  useState,
} from "react";
import {
  AlertTriangle,
  Eye,
  GripHorizontal,
  RotateCcw,
  ShieldCheck,
  X,
} from "lucide-react";

import { LatexFileChangeDiffPreview } from "@/components/latex/LatexFileChangeDiffPreview";
import { PrismReviewList } from "@/components/prism/PrismReviewList";
import { Button } from "@/components/ui/button";
import type {
  LatexAppliedFileChange,
  LatexFeedbackItem,
  LatexFeedbackRewriteCandidate,
  LatexFileChange,
  LatexFileChangePreviewResponse,
  WorkspacePrismReviewItem,
} from "@/lib/api";

import { LatexRewritePreviewPanel } from "./LatexRewritePreviewPanel";
import { PrismAnnotationComposer } from "./PrismAnnotationComposer";
import { PrismAnnotationList } from "./PrismAnnotationList";

type PrismAssistPanelPosition =
  | "bottom-right"
  | "top-right"
  | "bottom-left"
  | "bottom-center";

function panelPositionStyle(position: PrismAssistPanelPosition): CSSProperties {
  if (position === "top-right") {
    return { right: 16, top: 80 };
  }
  if (position === "bottom-left") {
    return { bottom: 16, left: 16 };
  }
  if (position === "bottom-center") {
    return { bottom: 16, left: "50%", transform: "translateX(-50%)" };
  }
  return { bottom: 16, right: 16 };
}

function snapPanelPosition(
  left: number,
  top: number,
  width: number,
  height: number,
): PrismAssistPanelPosition {
  if (typeof window === "undefined") {
    return "bottom-right";
  }
  const centerX = left + width / 2;
  const centerY = top + height / 2;
  const viewportWidth = window.innerWidth || 1280;
  const viewportHeight = window.innerHeight || 800;
  if (centerY < viewportHeight * 0.45) {
    return "top-right";
  }
  if (centerX < viewportWidth * 0.38) {
    return "bottom-left";
  }
  if (centerX > viewportWidth * 0.62) {
    return "bottom-right";
  }
  return "bottom-center";
}

export function PrismAssistPanel({
  open,
  contextText,
  draftComment,
  scope,
  canCreate,
  canUseDocumentAssist,
  canDeepAssist,
  hasSelectionContext,
  busy,
  isSaving,
  status,
  error,
  annotations,
  activeFeedbackId,
  selectedRewriteCandidate,
  selectedRewriteCandidateIndex,
  rewriteCandidates,
  diffViewMode,
  showWhitespaceOnlyDiff,
  collapsedDiffHunks,
  previewFeedbackItem,
  feedbackBusyId,
  isApplyingRewrite,
  runningJobCount,
  protectionStatus,
  protectionError,
  isProtectingActiveFile,
  canProtectActiveFile,
  hasUndoableRewrite,
  fileChangesRef,
  fileChanges,
  appliedFileChanges,
  pendingReviewItems,
  appliedReviewItems,
  focusedReviewItemId,
  focusedLogicalKey,
  fileChangePreviews,
  busyFileChangeKey,
  fileChangeError,
  onClose,
  onDraftChange,
  onScopeChange,
  onSaveComment,
  onQuickRewrite,
  onDeepAssist,
  onProtectActiveFile,
  onUndoRewrite,
  onFocusAnnotation,
  onQuickRewriteAnnotation,
  onDeepAssistAnnotation,
  onRemoveAnnotation,
  onSelectCandidate,
  onRegenerate,
  onDiffViewModeChange,
  onToggleWhitespaceOnlyDiff,
  onCollapseAllDiffHunks,
  onToggleDiffHunkCollapsed,
  onCopyRewrite,
  onCancelRewrite,
  onApplyRewrite,
  onPreviewProjectFileChange,
  onDiscardPendingFileChange,
  onApplyPendingFileChange,
  onRevertAppliedFileChange,
}: {
  open: boolean;
  contextText: string;
  draftComment: string;
  scope: "selection" | "section";
  canCreate: boolean;
  canUseDocumentAssist: boolean;
  canDeepAssist: boolean;
  hasSelectionContext: boolean;
  busy: boolean;
  isSaving: boolean;
  status: string;
  error: string;
  annotations: LatexFeedbackItem[];
  activeFeedbackId: string | null;
  selectedRewriteCandidate: LatexFeedbackRewriteCandidate | null;
  selectedRewriteCandidateIndex: number;
  rewriteCandidates: LatexFeedbackRewriteCandidate[];
  diffViewMode: "inline" | "side-by-side";
  showWhitespaceOnlyDiff: boolean;
  collapsedDiffHunks: Record<string, boolean>;
  previewFeedbackItem: LatexFeedbackItem | null;
  feedbackBusyId: string | null;
  isApplyingRewrite: boolean;
  runningJobCount: number;
  protectionStatus: string;
  protectionError: string;
  isProtectingActiveFile: boolean;
  canProtectActiveFile: boolean;
  hasUndoableRewrite?: boolean;
  fileChangesRef: RefObject<HTMLDivElement | null>;
  fileChanges: LatexFileChange[];
  appliedFileChanges: LatexAppliedFileChange[];
  pendingReviewItems: WorkspacePrismReviewItem[];
  appliedReviewItems: WorkspacePrismReviewItem[];
  focusedReviewItemId: string | null;
  focusedLogicalKey: string | null;
  fileChangePreviews: Record<string, LatexFileChangePreviewResponse>;
  busyFileChangeKey: string | null;
  fileChangeError: string;
  onClose: () => void;
  onDraftChange: (comment: string) => void;
  onScopeChange: (scope: "selection" | "section") => void;
  onSaveComment: () => void;
  onQuickRewrite: () => void;
  onDeepAssist: () => void;
  onProtectActiveFile: () => void;
  onUndoRewrite?: () => void;
  onFocusAnnotation: (item: LatexFeedbackItem) => void;
  onQuickRewriteAnnotation: (item: LatexFeedbackItem) => void;
  onDeepAssistAnnotation: (item: LatexFeedbackItem) => void;
  onRemoveAnnotation: (feedbackId: string) => void;
  onSelectCandidate: (candidateId: string) => void;
  onRegenerate: () => void;
  onDiffViewModeChange: (mode: "inline" | "side-by-side") => void;
  onToggleWhitespaceOnlyDiff: () => void;
  onCollapseAllDiffHunks: (collapsed: boolean) => void;
  onToggleDiffHunkCollapsed: (hunkKey: string) => void;
  onCopyRewrite: () => void;
  onCancelRewrite: () => void;
  onApplyRewrite: () => void;
  onPreviewProjectFileChange: (change: LatexFileChange) => void;
  onDiscardPendingFileChange: (change: LatexFileChange) => void;
  onApplyPendingFileChange: (change: LatexFileChange) => void;
  onRevertAppliedFileChange: (change: LatexAppliedFileChange) => void;
}) {
  const panelRef = useRef<HTMLElement | null>(null);
  const dragStateRef = useRef<{
    pointerId: number;
    offsetX: number;
    offsetY: number;
    width: number;
    height: number;
  } | null>(null);
  const [panelPosition, setPanelPosition] =
    useState<PrismAssistPanelPosition>("bottom-right");
  const [dragStyle, setDragStyle] = useState<CSSProperties | null>(null);

  if (!open) {
    return null;
  }

  const isFileChangeBusy = (logicalKey: string) =>
    isSaving || busyFileChangeKey === logicalKey;
  const hasAssistComposer = Boolean(
    canUseDocumentAssist ||
      hasSelectionContext ||
      canCreate ||
      draftComment.trim(),
  );
  const hasRewritePreview = Boolean(selectedRewriteCandidate || rewriteCandidates.length > 0);
  const hasReviewQueue = Boolean(
    fileChanges.length > 0 ||
      appliedFileChanges.length > 0 ||
      fileChangeError,
  );
  const hasFileSafetyState = Boolean(
    protectionStatus ||
      protectionError ||
      hasUndoableRewrite ||
      fileChanges.length > 0 ||
      appliedFileChanges.length > 0,
  );
  const hasAnnotations = annotations.length > 0;
  const shouldShowEmptyState = !hasAssistComposer &&
    !hasRewritePreview &&
    !hasReviewQueue &&
    !hasFileSafetyState &&
    !hasAnnotations &&
    !status &&
    !error &&
    runningJobCount === 0;
  const effectivePanelStyle = dragStyle ?? panelPositionStyle(panelPosition);
  const beginPanelDrag = (event: PointerEvent<HTMLElement>) => {
    const target = event.target as HTMLElement;
    if (target.closest("button,textarea,select,input,a")) {
      return;
    }
    const panel = panelRef.current;
    if (!panel) {
      return;
    }
    const rect = panel.getBoundingClientRect();
    dragStateRef.current = {
      pointerId: event.pointerId,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
      width: rect.width,
      height: rect.height,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragStyle({
      left: rect.left,
      top: rect.top,
      right: "auto",
      bottom: "auto",
      transform: "none",
    });
  };
  const movePanelDrag = (event: PointerEvent<HTMLElement>) => {
    const drag = dragStateRef.current;
    if (!drag) {
      return;
    }
    const maxLeft = Math.max(12, window.innerWidth - drag.width - 12);
    const maxTop = Math.max(72, window.innerHeight - drag.height - 12);
    const left = Math.min(Math.max(12, event.clientX - drag.offsetX), maxLeft);
    const top = Math.min(Math.max(72, event.clientY - drag.offsetY), maxTop);
    setDragStyle({
      left,
      top,
      right: "auto",
      bottom: "auto",
      transform: "none",
    });
  };
  const endPanelDrag = (event: PointerEvent<HTMLElement>) => {
    const drag = dragStateRef.current;
    if (!drag) {
      return;
    }
    const panel = panelRef.current;
    const rect = panel?.getBoundingClientRect();
    const nextPosition = rect
      ? snapPanelPosition(rect.left, rect.top, rect.width, rect.height)
      : "bottom-right";
    dragStateRef.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
    setDragStyle(null);
    setPanelPosition(nextPosition);
  };
  const resetPanelPosition = () => {
    dragStateRef.current = null;
    setDragStyle(null);
    setPanelPosition("bottom-right");
  };

  return (
    <aside
      ref={panelRef}
      role="dialog"
      aria-modal="false"
      aria-label="改稿助手"
      data-position={panelPosition}
      className="fixed z-50 flex max-h-[min(72vh,680px)] w-[min(420px,calc(100vw-24px))] flex-col overflow-hidden rounded-xl border border-white/75 bg-white/90 shadow-[var(--wjn-shadow-lg)] backdrop-blur-xl"
      style={effectivePanelStyle}
    >
      <div
        className="flex min-h-12 shrink-0 cursor-move select-none items-center justify-between gap-3 border-b border-[var(--wjn-line)] bg-white/72 px-3 py-2"
        title="拖动移动改稿助手面板"
        onPointerDown={beginPanelDrag}
        onPointerMove={movePanelDrag}
        onPointerUp={endPanelDrag}
        onPointerCancel={endPanelDrag}
      >
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-sm font-semibold text-[var(--wjn-text)]">
            <GripHorizontal className="h-3.5 w-3.5 text-[var(--wjn-text-muted)]" aria-hidden="true" />
            改稿助手
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            size="sm"
            variant="outline"
            onClick={resetPanelPosition}
            aria-label="重置改稿助手面板位置"
            title="重置改稿助手面板位置"
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onClose}
            aria-label="关闭改稿助手"
            title="关闭改稿助手"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-auto p-2.5">
        {hasAssistComposer ? (
          <PrismAnnotationComposer
            contextText={contextText}
            draftComment={draftComment}
            scope={scope}
            canCreate={canCreate}
            canUseDocumentAssist={canUseDocumentAssist}
            canDeepAssist={canDeepAssist}
            hasSelectionContext={hasSelectionContext}
            busy={busy}
            onDraftChange={onDraftChange}
            onScopeChange={onScopeChange}
            onSaveComment={onSaveComment}
            onQuickRewrite={onQuickRewrite}
            onDeepAssist={onDeepAssist}
          />
        ) : null}

        {shouldShowEmptyState ? (
          <section className="rounded-lg border border-[var(--wjn-line)] bg-white/72 px-3 py-4">
            <p className="text-sm font-semibold text-[var(--wjn-text)]">待命中</p>
            <p className="mt-1 text-xs leading-5 text-[var(--wjn-text-muted)]">
              打开可编辑 TeX 后可输入全文指令；划线后可添加批注或改这段。
            </p>
          </section>
        ) : null}

        {hasFileSafetyState ? (
          <section className="rounded-lg border border-[var(--wjn-line)] bg-white/78 p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-[var(--wjn-text)]">文件安全</p>
                <p className="mt-1 text-xs leading-5 text-[var(--wjn-text-muted)]">
                  保护当前文件后，团队改稿会先生成建议，不直接覆盖正文。
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={onProtectActiveFile}
                disabled={isProtectingActiveFile || !canProtectActiveFile}
              >
                <ShieldCheck className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                {isProtectingActiveFile ? "保护中..." : "保护当前文件"}
              </Button>
            </div>
            {protectionStatus ? (
              <div className="mt-3 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs leading-5 text-emerald-700">
                {protectionStatus}
              </div>
            ) : null}
            {protectionError ? (
              <div className="mt-3 rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs leading-5 text-red-700">
                {protectionError}
              </div>
            ) : null}
            {hasUndoableRewrite && onUndoRewrite ? (
              <div className="mt-3 flex items-center justify-between gap-3 rounded-lg border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] px-3 py-2">
                <p className="text-xs text-[var(--wjn-text-muted)]">可撤销最近一次改稿。</p>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={onUndoRewrite}
                  disabled={isApplyingRewrite || isSaving}
                >
                  {isApplyingRewrite ? "处理中..." : "撤销"}
                </Button>
              </div>
            ) : null}
          </section>
        ) : null}

        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs leading-5 text-red-700">
            {error}
          </div>
        ) : null}
        {status ? (
          <div className="rounded-lg border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] px-3 py-2 text-xs leading-5 text-[var(--wjn-text-secondary)]">
            {status}
          </div>
        ) : null}
        {runningJobCount > 0 ? (
          <div className="rounded-lg border border-[var(--wjn-accent-line)] bg-[var(--wjn-accent-soft)] px-3 py-2 text-xs leading-5 text-[var(--wjn-accent-strong)]">
            团队处理中 · {runningJobCount} 个任务
          </div>
        ) : null}

        {hasReviewQueue ? (
          <section ref={fileChangesRef} className="space-y-3 rounded-lg border border-[var(--wjn-line)] bg-white/78 p-3">
            <div>
              <div className="flex items-center gap-2">
                {fileChanges.length > 0 ? (
                  <AlertTriangle className="h-4 w-4 text-amber-700" aria-hidden="true" />
                ) : null}
                <p className="text-sm font-semibold text-[var(--wjn-text)]">待复核写入</p>
                {fileChanges.length > 0 ? (
                  <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-800">
                    {fileChanges.length}
                  </span>
                ) : null}
              </div>
              <p className="mt-1 text-xs leading-5 text-[var(--wjn-text-muted)]">
                全文改稿和工作台生成的稿件修改都会先预览 diff，再由你决定是否应用。
              </p>
            </div>
            {fileChangeError ? (
              <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs leading-5 text-red-700">
                {fileChangeError}
              </div>
            ) : null}
            <PrismReviewList
              items={pendingReviewItems}
              emptyMessage="暂无待复核写入。"
              focusedItemId={focusedReviewItemId}
              focusedLogicalKey={focusedLogicalKey}
              renderActions={(item) => {
                const change = fileChanges.find(
                  (entry) => entry.logical_key === item.logical_key,
                );
                if (!change) return null;
                const preview = fileChangePreviews[change.logical_key] ?? null;
                const isBusy = isFileChangeBusy(change.logical_key);
                return (
                  <>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onPreviewProjectFileChange(change)}
                      disabled={isBusy}
                    >
                      <Eye className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                      {busyFileChangeKey === change.logical_key
                        ? "处理中..."
                        : preview
                          ? "刷新 diff"
                          : "预览 diff"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onDiscardPendingFileChange(change)}
                      disabled={isBusy}
                    >
                      忽略
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => onApplyPendingFileChange(change)}
                      disabled={isBusy}
                    >
                      应用
                    </Button>
                  </>
                );
              }}
              renderDetails={(item) => {
                const preview = item.logical_key
                  ? (fileChangePreviews[item.logical_key] ?? null)
                  : null;
                return preview ? (
                  <LatexFileChangeDiffPreview
                    preview={preview}
                    maxOps={8}
                    className="mt-3"
                  />
                ) : null;
              }}
            />
            {appliedFileChanges.length > 0 ? (
              <div className="border-t border-[rgba(15,23,42,0.08)] pt-3">
                <p className="mb-2 text-xs font-semibold text-[var(--wjn-text-muted)]">
                  已写入变更
                </p>
                <PrismReviewList
                  items={appliedReviewItems}
                  focusedItemId={focusedReviewItemId}
                  focusedLogicalKey={focusedLogicalKey}
                  renderActions={(item) => {
                    const change = appliedFileChanges.find(
                      (entry) => entry.logical_key === item.logical_key,
                    );
                    if (!change) return null;
                    const isBusy = isFileChangeBusy(change.logical_key);
                    return (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onRevertAppliedFileChange(change)}
                        disabled={isBusy}
                      >
                        <RotateCcw className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                        {busyFileChangeKey === change.logical_key ? "撤回中..." : "撤回"}
                      </Button>
                    );
                  }}
                />
              </div>
            ) : null}
          </section>
        ) : null}

        {hasRewritePreview ? (
          <LatexRewritePreviewPanel
            selectedRewriteCandidate={selectedRewriteCandidate}
            selectedRewriteCandidateIndex={selectedRewriteCandidateIndex}
            rewriteCandidates={rewriteCandidates}
            diffViewMode={diffViewMode}
            showWhitespaceOnlyDiff={showWhitespaceOnlyDiff}
            collapsedDiffHunks={collapsedDiffHunks}
            previewFeedbackItem={previewFeedbackItem}
            feedbackBusyId={feedbackBusyId}
            isApplyingRewrite={isApplyingRewrite}
            isSaving={isSaving}
            onSelectCandidate={onSelectCandidate}
            onRegenerate={onRegenerate}
            onDiffViewModeChange={onDiffViewModeChange}
            onToggleWhitespaceOnlyDiff={onToggleWhitespaceOnlyDiff}
            onCollapseAll={onCollapseAllDiffHunks}
            onToggleHunkCollapsed={onToggleDiffHunkCollapsed}
            onCopy={onCopyRewrite}
            onCancel={onCancelRewrite}
            onApply={onApplyRewrite}
          />
        ) : null}

        {hasAnnotations ? (
          <PrismAnnotationList
            annotations={annotations}
            activeFeedbackId={activeFeedbackId}
            busyFeedbackId={feedbackBusyId}
            onFocus={onFocusAnnotation}
            onQuickRewrite={onQuickRewriteAnnotation}
            onDeepAssist={onDeepAssistAnnotation}
            onRemove={onRemoveAnnotation}
          />
        ) : null}
      </div>
    </aside>
  );
}
