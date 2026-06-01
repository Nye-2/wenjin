import type { RefObject } from "react";
import {
  AlertTriangle,
  Eye,
  RotateCcw,
  ShieldCheck,
  X,
} from "lucide-react";

import { LatexFileChangeDiffPreview } from "@/components/latex/LatexFileChangeDiffPreview";
import { PrismReviewList } from "@/components/prism/PrismReviewList";
import { Button } from "@/components/ui/button";
import type {
  LatexAppliedFileChange,
  LatexCompileEngine,
  LatexCompileResult,
  LatexFeedbackItem,
  LatexFeedbackRewriteCandidate,
  LatexFileChange,
  LatexFileChangePreviewResponse,
  WorkspacePrismReviewItem,
} from "@/lib/api";
import {
  prismJobStatusLabel,
  trimSnippet,
  type PrismOptimizationJob,
} from "./prismOptimizationJobs";
import { LatexRewritePreviewPanel } from "./LatexRewritePreviewPanel";
import type {
  LastRewriteUndoState,
  PrismInspectorTab,
  PrismSurfaceMode,
} from "./types";

interface InspectorTabItem {
  id: PrismInspectorTab;
  label: string;
  badge?: number;
}

export function LatexInspector({
  isOpen,
  surfaceMode,
  activeTab,
  tabs,
  feedbackContextText,
  feedbackDraftComment,
  feedbackScope,
  canCreateFeedback,
  isSaving,
  isChatSending,
  feedbackBusyId,
  feedbackError,
  feedbackStatus,
  protectionStatus,
  protectionError,
  isProtectingActiveFile,
  activeFilePath,
  activeFileKind,
  lastRewriteUndo,
  isApplyingRewrite,
  selectedRewriteCandidate,
  selectedRewriteCandidateIndex,
  rewriteCandidates,
  diffViewMode,
  showWhitespaceOnlyDiff,
  collapsedDiffHunks,
  previewFeedbackItem,
  feedbackLoaded,
  currentFileFeedbacks,
  activeFeedbackId,
  optimizingFeedbackIds,
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
  engineHint,
  isCompiling,
  engine,
  mainFile,
  compileResult,
  canOpenCompileLog,
  activePrismOptimizationJob,
  onTabChange,
  onClose,
  onFeedbackDraftCommentChange,
  onFeedbackScopeChange,
  onAddFeedbackAndRewrite,
  onAddFeedbackOnly,
  onProtectActiveFile,
  onUndoLastRewrite,
  onSelectRewriteCandidate,
  onRegenerateRewrite,
  onDiffViewModeChange,
  onToggleWhitespaceOnlyDiff,
  onCollapseAllDiffHunks,
  onToggleDiffHunkCollapsed,
  onCopySelectedRewrite,
  onCancelRewritePreview,
  onApplyRewriteCandidate,
  onFocusFeedback,
  onRewriteFromFeedback,
  onLaunchPrismOptimization,
  onRemoveFeedback,
  onPreviewProjectFileChange,
  onDiscardPendingFileChange,
  onApplyPendingFileChange,
  onRevertAppliedFileChange,
  onOpenCompileLog,
  onOpenTrace,
}: {
  isOpen: boolean;
  surfaceMode: PrismSurfaceMode;
  activeTab: PrismInspectorTab;
  tabs: InspectorTabItem[];
  feedbackContextText: string;
  feedbackDraftComment: string;
  feedbackScope: "selection" | "section";
  canCreateFeedback: boolean;
  isSaving: boolean;
  isChatSending: boolean;
  feedbackBusyId: string | null;
  feedbackError: string;
  feedbackStatus: string;
  protectionStatus: string;
  protectionError: string;
  isProtectingActiveFile: boolean;
  activeFilePath: string | null;
  activeFileKind: "text" | "blob" | null;
  lastRewriteUndo: LastRewriteUndoState | null;
  isApplyingRewrite: boolean;
  selectedRewriteCandidate: LatexFeedbackRewriteCandidate | null;
  selectedRewriteCandidateIndex: number;
  rewriteCandidates: LatexFeedbackRewriteCandidate[];
  diffViewMode: "inline" | "side-by-side";
  showWhitespaceOnlyDiff: boolean;
  collapsedDiffHunks: Record<string, boolean>;
  previewFeedbackItem: LatexFeedbackItem | null;
  feedbackLoaded: boolean;
  currentFileFeedbacks: LatexFeedbackItem[];
  activeFeedbackId: string | null;
  optimizingFeedbackIds: Set<string>;
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
  engineHint: string;
  isCompiling: boolean;
  engine: LatexCompileEngine;
  mainFile?: string | null;
  compileResult: LatexCompileResult | null;
  canOpenCompileLog: boolean;
  activePrismOptimizationJob: PrismOptimizationJob | null;
  onTabChange: (tab: PrismInspectorTab) => void;
  onClose: () => void;
  onFeedbackDraftCommentChange: (comment: string) => void;
  onFeedbackScopeChange: (scope: "selection" | "section") => void;
  onAddFeedbackAndRewrite: () => void;
  onAddFeedbackOnly: () => void;
  onProtectActiveFile: () => void;
  onUndoLastRewrite: () => void;
  onSelectRewriteCandidate: (candidateId: string) => void;
  onRegenerateRewrite: () => void;
  onDiffViewModeChange: (mode: "inline" | "side-by-side") => void;
  onToggleWhitespaceOnlyDiff: () => void;
  onCollapseAllDiffHunks: (collapsed: boolean) => void;
  onToggleDiffHunkCollapsed: (hunkKey: string) => void;
  onCopySelectedRewrite: () => void;
  onCancelRewritePreview: () => void;
  onApplyRewriteCandidate: () => void;
  onFocusFeedback: (item: LatexFeedbackItem) => void;
  onRewriteFromFeedback: (item: LatexFeedbackItem) => void;
  onLaunchPrismOptimization: (item: LatexFeedbackItem) => void;
  onRemoveFeedback: (feedbackId: string) => void;
  onPreviewProjectFileChange: (change: LatexFileChange) => void;
  onDiscardPendingFileChange: (change: LatexFileChange) => void;
  onApplyPendingFileChange: (change: LatexFileChange) => void;
  onRevertAppliedFileChange: (change: LatexAppliedFileChange) => void;
  onOpenCompileLog: () => void;
  onOpenTrace: () => void;
}) {
  if (!isOpen || surfaceMode === "focus") {
    return null;
  }

  const renderFeedbackInspector = () => (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-medium">划词点评与 Agent 优化</p>
        <p className="mt-1 text-xs leading-5 text-[var(--text-muted)]">{feedbackContextText}</p>
      </div>
      <textarea
        value={feedbackDraftComment}
        onChange={(event) => onFeedbackDraftCommentChange(event.target.value)}
        placeholder="例如：这一段贡献点不够清晰，请加强问题定义和定量结论。"
        className="min-h-[112px] w-full resize-none rounded-lg border border-[var(--border-default)] bg-white px-3 py-2 text-sm leading-6 outline-none focus:border-[var(--v2-accent-purple-300)]"
      />
      <div className="grid gap-2">
        <label className="text-xs text-[var(--text-muted)]">优化范围</label>
        <select
          value={feedbackScope}
          onChange={(event) => onFeedbackScopeChange(event.target.value as "selection" | "section")}
          className="h-9 rounded-lg border border-[var(--border-default)] bg-white px-2 text-sm"
        >
          <option value="section">重写所在 section</option>
          <option value="selection">仅重写选区</option>
        </select>
      </div>
      <div className="grid gap-2">
        <Button
          disabled={!canCreateFeedback || isSaving || isChatSending || Boolean(feedbackBusyId)}
          onClick={onAddFeedbackAndRewrite}
        >
          {feedbackBusyId ? "提交中..." : "交给 Agent 优化"}
        </Button>
        <Button
          variant="outline"
          disabled={!canCreateFeedback || isSaving}
          onClick={onAddFeedbackOnly}
        >
          只保存点评
        </Button>
        <Button
          variant="outline"
          onClick={onProtectActiveFile}
          disabled={isProtectingActiveFile || !activeFilePath || activeFileKind !== "text"}
        >
          <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
          {isProtectingActiveFile ? "保护中..." : "保护当前文件"}
        </Button>
      </div>
      {feedbackError ? (
        <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-700">
          {feedbackError}
        </div>
      ) : null}
      {feedbackStatus ? (
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700">
          {feedbackStatus}
        </div>
      ) : null}
      {protectionStatus ? (
        <div className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700">
          {protectionStatus}
        </div>
      ) : null}
      {protectionError ? (
        <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-700">
          {protectionError}
        </div>
      ) : null}
      {lastRewriteUndo ? (
        <div className="flex items-center justify-between gap-2 rounded-lg border border-[var(--border-default)] bg-white px-3 py-2">
          <p className="text-xs text-[var(--text-muted)]">可撤销最近一次本地改写。</p>
          <Button
            size="sm"
            variant="outline"
            onClick={onUndoLastRewrite}
            disabled={isApplyingRewrite || isSaving}
          >
            {isApplyingRewrite ? "处理中..." : "撤销"}
          </Button>
        </div>
      ) : null}
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
        onSelectCandidate={onSelectRewriteCandidate}
        onRegenerate={onRegenerateRewrite}
        onDiffViewModeChange={onDiffViewModeChange}
        onToggleWhitespaceOnlyDiff={onToggleWhitespaceOnlyDiff}
        onCollapseAll={onCollapseAllDiffHunks}
        onToggleHunkCollapsed={onToggleDiffHunkCollapsed}
        onCopy={onCopySelectedRewrite}
        onCancel={onCancelRewritePreview}
        onApply={onApplyRewriteCandidate}
      />
      <div className="border-t border-[rgba(15,23,42,0.08)] pt-3">
        <p className="mb-2 text-xs font-semibold text-[var(--text-muted)]">
          当前文件点评
        </p>
        {!feedbackLoaded ? (
          <div className="text-xs text-[var(--text-muted)]">加载点评中...</div>
        ) : currentFileFeedbacks.length === 0 ? (
          <div className="text-xs text-[var(--text-muted)]">当前文件还没有点评。</div>
        ) : (
          <div className="space-y-2">
            {currentFileFeedbacks.map((item, index) => (
              <div
                key={item.id}
                className={`rounded-lg border px-3 py-2 ${
                  activeFeedbackId === item.id
                    ? "border-[var(--v2-accent-purple-300)] bg-[rgba(124,92,255,0.08)]"
                    : "border-[var(--border-default)] bg-white"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs font-medium">点评 #{index + 1}</p>
                  <div className="text-[11px] text-[var(--text-muted)]">
                    {item.last_status === "error"
                      ? "失败"
                      : item.last_status === "pending"
                        ? "处理中"
                        : item.last_status === "done"
                          ? "已采纳"
                          : "已保存"}
                  </div>
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-[var(--text-muted)]">
                  {item.selected_text}
                </p>
                <p className="mt-1 text-sm leading-5">{item.comment}</p>
                {item.last_error ? (
                  <p className="mt-1 text-xs text-red-600">{item.last_error}</p>
                ) : null}
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => onFocusFeedback(item)}>
                    定位
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onRewriteFromFeedback(item)}
                    disabled={feedbackBusyId === item.id || isApplyingRewrite}
                  >
                    {feedbackBusyId === item.id ? "生成中..." : "生成 diff"}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => onLaunchPrismOptimization(item)}
                    disabled={
                      feedbackBusyId === item.id ||
                      isApplyingRewrite ||
                      isChatSending ||
                      optimizingFeedbackIds.has(item.id)
                    }
                  >
                    {feedbackBusyId === item.id || optimizingFeedbackIds.has(item.id)
                      ? "优化中..."
                      : "Agent 优化"}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => onRemoveFeedback(item.id)}>
                    删除
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  const renderReviewInspector = () => (
    <div ref={fileChangesRef} className="space-y-4">
      <div>
        <div className="flex items-center gap-2">
          {fileChanges.length > 0 ? (
            <AlertTriangle className="h-4 w-4 text-amber-700" />
          ) : null}
          <p className="text-sm font-medium">Prism 审阅</p>
        </div>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          待确认写入会先预览 diff，再由你决定是否应用。
        </p>
      </div>
      {fileChangeError ? (
        <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-700">
          {fileChangeError}
        </div>
      ) : null}
      {fileChanges.length > 0 ? (
        <PrismReviewList
          items={pendingReviewItems}
          focusedItemId={focusedReviewItemId}
          focusedLogicalKey={focusedLogicalKey}
          renderActions={(item) => {
            const change = fileChanges.find(
              (entry) => entry.logical_key === item.logical_key,
            );
            if (!change) return null;
            const preview = fileChangePreviews[change.logical_key] ?? null;
            const isBusy = isSaving || busyFileChangeKey === change.logical_key;
            return (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onPreviewProjectFileChange(change)}
                  disabled={isBusy}
                >
                  <Eye className="mr-1.5 h-3.5 w-3.5" />
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
            const preview = fileChangePreviews[item.logical_key] ?? null;
            return preview ? (
              <LatexFileChangeDiffPreview
                preview={preview}
                maxOps={8}
                className="mt-3"
              />
            ) : null;
          }}
        />
      ) : (
        <div className="rounded-lg border border-dashed border-[var(--border-default)] bg-white px-3 py-6 text-center text-xs text-[var(--text-muted)]">
          暂无待确认写入。
        </div>
      )}
      {appliedFileChanges.length > 0 ? (
        <div className="border-t border-[rgba(15,23,42,0.08)] pt-3">
          <p className="mb-2 text-xs font-semibold text-[var(--text-muted)]">已写入变更</p>
          <PrismReviewList
            items={appliedReviewItems}
            focusedItemId={focusedReviewItemId}
            focusedLogicalKey={focusedLogicalKey}
            renderActions={(item) => {
              const change = appliedFileChanges.find(
                (entry) => entry.logical_key === item.logical_key,
              );
              if (!change) return null;
              const isBusy = isSaving || busyFileChangeKey === change.logical_key;
              return (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onRevertAppliedFileChange(change)}
                  disabled={isBusy}
                >
                  <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                  {busyFileChangeKey === change.logical_key ? "撤回中..." : "撤回"}
                </Button>
              );
            }}
          />
        </div>
      ) : null}
    </div>
  );

  const renderCompileInspector = () => (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-medium">编译状态</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">{engineHint}</p>
      </div>
      <div className="rounded-lg border border-[var(--border-default)] bg-white px-3 py-3 text-sm text-[var(--text-secondary)]">
        {isCompiling
          ? `正在编译：${engine} · ${mainFile || "main.tex"}`
          : compileResult
            ? `最近一次编译：${compileResult.ok ? "成功" : "失败"} · ${compileResult.engine} · ${compileResult.main_file}`
            : "当前还没有编译记录。"}
      </div>
      <Button
        variant="outline"
        onClick={onOpenCompileLog}
        disabled={!canOpenCompileLog}
        className="w-full"
      >
        查看后台详情
      </Button>
      {compileResult?.error ? (
        <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs leading-5 text-red-700">
          {compileResult.error}
        </div>
      ) : null}
    </div>
  );

  const renderAgentInspector = () => (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-medium">Agent 任务</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          Prism 内只展示轻量过程，完整运行记录在 Workbench。
        </p>
      </div>
      {activePrismOptimizationJob ? (
        <div className="rounded-lg border border-[var(--border-default)] bg-white p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-medium">
              {prismJobStatusLabel(activePrismOptimizationJob.status)}
            </p>
            <span className="rounded-full bg-[rgba(124,92,255,0.1)] px-2 py-0.5 text-[11px] text-[var(--v2-accent-purple-700)]">
              {activePrismOptimizationJob.scope === "section" ? "section" : "selection"}
            </span>
          </div>
          <p className="mt-2 text-xs leading-5 text-[var(--text-muted)]">
            {trimSnippet(activePrismOptimizationJob.selectedText, 180)}
          </p>
          <Button
            className="mt-3 w-full"
            size="sm"
            onClick={onOpenTrace}
          >
            查看工作过程
          </Button>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-[var(--border-default)] bg-white px-3 py-6 text-center text-xs text-[var(--text-muted)]">
          当前没有 Prism 内任务。
        </div>
      )}
    </div>
  );

  return (
    <aside className="fixed inset-x-3 bottom-3 z-30 flex max-h-[72vh] flex-col rounded-xl border border-[var(--wjn-line-strong)] bg-[var(--wjn-bg-rail)] shadow-2xl xl:static xl:inset-auto xl:z-auto xl:max-h-none xl:w-[360px] xl:shrink-0 xl:rounded-none xl:border-y-0 xl:border-r-0 xl:shadow-none">
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--wjn-line)] px-3">
        <div className="inline-flex rounded-[10px] border border-[var(--wjn-line)] bg-white p-0.5">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => onTabChange(tab.id)}
              className={`inline-flex items-center gap-1 rounded px-2 py-1 text-xs ${
                activeTab === tab.id
                  ? "bg-[var(--wjn-surface-subtle)] text-[var(--wjn-text)]"
                  : "text-[var(--wjn-text-muted)]"
              }`}
            >
              {tab.label}
              {tab.badge ? (
                <span className="rounded-full bg-white px-1.5 text-[10px]">{tab.badge}</span>
              ) : null}
            </button>
          ))}
        </div>
        <Button size="sm" variant="outline" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {activeTab === "assist"
          ? renderFeedbackInspector()
          : activeTab === "review"
            ? renderReviewInspector()
            : activeTab === "compile"
              ? renderCompileInspector()
              : renderAgentInspector()}
      </div>
    </aside>
  );
}
