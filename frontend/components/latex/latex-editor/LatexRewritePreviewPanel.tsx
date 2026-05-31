import type { LatexFeedbackItem, LatexFeedbackRewriteCandidate } from "@/lib/api";
import { Button } from "@/components/ui/button";

import {
  diffOpLabel,
  isWhitespaceOnlyDiffOp,
  rewriteProfileLabel,
  riskFlagClass,
  riskFlagLabel,
  riskLevelClass,
  riskLevelLabel,
  tokenKindLabel,
} from "./rewriteDisplay";

export function LatexRewritePreviewPanel({
  selectedRewriteCandidate,
  selectedRewriteCandidateIndex,
  rewriteCandidates,
  diffViewMode,
  showWhitespaceOnlyDiff,
  collapsedDiffHunks,
  previewFeedbackItem,
  feedbackBusyId,
  isApplyingRewrite,
  isSaving,
  onSelectCandidate,
  onRegenerate,
  onDiffViewModeChange,
  onToggleWhitespaceOnlyDiff,
  onCollapseAll,
  onToggleHunkCollapsed,
  onCopy,
  onCancel,
  onApply,
}: {
  selectedRewriteCandidate: LatexFeedbackRewriteCandidate | null;
  selectedRewriteCandidateIndex: number;
  rewriteCandidates: LatexFeedbackRewriteCandidate[];
  diffViewMode: "inline" | "side-by-side";
  showWhitespaceOnlyDiff: boolean;
  collapsedDiffHunks: Record<string, boolean>;
  previewFeedbackItem: LatexFeedbackItem | null;
  feedbackBusyId: string | null;
  isApplyingRewrite: boolean;
  isSaving: boolean;
  onSelectCandidate: (candidateId: string) => void;
  onRegenerate: () => void;
  onDiffViewModeChange: (mode: "inline" | "side-by-side") => void;
  onToggleWhitespaceOnlyDiff: () => void;
  onCollapseAll: (collapsed: boolean) => void;
  onToggleHunkCollapsed: (hunkKey: string) => void;
  onCopy: () => void;
  onCancel: () => void;
  onApply: () => void;
}) {
  if (!selectedRewriteCandidate) {
    return null;
  }

  return (
    <div className="rounded-lg border border-[var(--border-default)] bg-white p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium">改写 diff 预览</p>
          <p className="mt-1 text-[11px] text-[var(--text-muted)]">
            候选 {selectedRewriteCandidateIndex + 1}/{rewriteCandidates.length} · Cmd/Ctrl + Enter 应用 · Esc 取消
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={selectedRewriteCandidate.candidate_id}
            onChange={(event) => onSelectCandidate(event.target.value)}
            className="h-8 rounded-md border border-[var(--border-default)] bg-white px-2 text-xs"
          >
            {rewriteCandidates.map((candidate, index) => (
              <option key={candidate.candidate_id} value={candidate.candidate_id}>
                候选 {index + 1} · {rewriteProfileLabel(candidate.profile)} · {riskLevelLabel(candidate.risk_level)}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            variant="outline"
            onClick={onRegenerate}
            disabled={!previewFeedbackItem || Boolean(feedbackBusyId) || isApplyingRewrite}
          >
            {feedbackBusyId ? "重生成中..." : "重生成"}
          </Button>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-muted)]">
        <span>
          {selectedRewriteCandidate.scope === "section"
            ? `section：${selectedRewriteCandidate.section_title || "未命名"}`
            : "仅选区"}
        </span>
        <span>风格：{rewriteProfileLabel(selectedRewriteCandidate.profile)}</span>
        <span className={`inline-flex rounded-full border px-1.5 py-0.5 ${riskLevelClass(selectedRewriteCandidate.risk_level)}`}>
          {riskLevelLabel(selectedRewriteCandidate.risk_level)}
        </span>
        <span>
          token {selectedRewriteCandidate.diff.stats.tokens_changed} · +{selectedRewriteCandidate.diff.stats.chars_added} / -{selectedRewriteCandidate.diff.stats.chars_deleted}
        </span>
      </div>

      {selectedRewriteCandidate.changes_summary.trim() ? (
        <p className="mt-2 rounded-md border border-[var(--border-default)] bg-[#f8f9fb] px-2 py-1 text-xs leading-5 text-[var(--text-secondary)]">
          模型摘要：{selectedRewriteCandidate.changes_summary.trim()}
        </p>
      ) : null}

      {selectedRewriteCandidate.diff.risk_flags.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {selectedRewriteCandidate.diff.risk_flags.map((flag) => (
            <span
              key={flag}
              className={`rounded-full border px-2 py-0.5 text-[10px] ${riskFlagClass(flag)}`}
            >
              {riskFlagLabel(flag)}
            </span>
          ))}
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => onDiffViewModeChange("inline")}
          className={diffViewMode === "inline" ? "bg-[#eef0f3]" : ""}
        >
          Inline
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => onDiffViewModeChange("side-by-side")}
          className={diffViewMode === "side-by-side" ? "bg-[#eef0f3]" : ""}
        >
          对照
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onToggleWhitespaceOnlyDiff}
        >
          {showWhitespaceOnlyDiff ? "隐藏空白" : "显示空白"}
        </Button>
        <Button size="sm" variant="outline" onClick={() => onCollapseAll(true)}>
          折叠
        </Button>
        <Button size="sm" variant="outline" onClick={() => onCollapseAll(false)}>
          展开
        </Button>
      </div>

      <div className="mt-3 max-h-[360px] space-y-2 overflow-auto rounded-lg border border-[var(--border-default)] bg-[#f8f9fb] p-2">
        {selectedRewriteCandidate.diff.hunks.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">未检测到文本差异。</p>
        ) : (
          selectedRewriteCandidate.diff.hunks.map((hunk, index) => {
            const hunkKey = `${hunk.old_start}-${hunk.old_end}-${hunk.new_start}-${hunk.new_end}-${index}`;
            const changedOps = hunk.ops.filter((op) => op.op !== "equal");
            const hiddenWhitespaceCount = changedOps.filter((op) => isWhitespaceOnlyDiffOp(op)).length;
            const visibleOps = showWhitespaceOnlyDiff
              ? changedOps
              : changedOps.filter((op) => !isWhitespaceOnlyDiffOp(op));
            const isCollapsed = Boolean(collapsedDiffHunks[hunkKey]);
            return (
              <div key={hunkKey} className="rounded-md border border-[var(--border-default)] bg-white p-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[11px] text-[var(--text-muted)]">
                    Hunk #{index + 1} · old {hunk.old_start}-{hunk.old_end} · new {hunk.new_start}-{hunk.new_end}
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onToggleHunkCollapsed(hunkKey)}
                  >
                    {isCollapsed ? "展开" : "折叠"}
                  </Button>
                </div>
                <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                  token {hunk.stats.tokens_changed} · +{hunk.stats.chars_added} / -{hunk.stats.chars_deleted}
                  {hiddenWhitespaceCount > 0 && !showWhitespaceOnlyDiff
                    ? ` · 已隐藏空白改动 ${hiddenWhitespaceCount} 条`
                    : ""}
                </p>
                {hunk.risk_flags.length > 0 ? (
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {hunk.risk_flags.map((flag) => (
                      <span key={flag} className={`rounded-full border px-2 py-0.5 text-[10px] ${riskFlagClass(flag)}`}>
                        {riskFlagLabel(flag)}
                      </span>
                    ))}
                  </div>
                ) : null}
                {!isCollapsed ? (
                  visibleOps.length > 0 ? (
                    <div className="mt-2 space-y-2">
                      {visibleOps.map((op, opIndex) => (
                        <div key={`${op.old_start}-${op.new_start}-${opIndex}`} className="text-xs leading-5">
                          <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[10px] text-[var(--text-muted)]">
                            <span className="rounded border border-[var(--border-default)] bg-white px-1.5 py-0.5">
                              {diffOpLabel(op.op)}
                            </span>
                            <span className="rounded border border-[var(--border-default)] bg-white px-1.5 py-0.5">
                              {tokenKindLabel(op.token_kind)}
                            </span>
                            {isWhitespaceOnlyDiffOp(op) ? (
                              <span className="rounded border border-[var(--border-default)] bg-white px-1.5 py-0.5">
                                仅空白
                              </span>
                            ) : null}
                          </div>
                          {diffViewMode === "side-by-side" ? (
                            <div className="grid gap-2 md:grid-cols-2">
                              <pre className={`overflow-x-auto whitespace-pre-wrap break-words rounded px-2 py-1 font-mono text-[12px] ${op.op === "insert" ? "bg-[rgba(19,34,53,0.04)] text-[var(--text-muted)]" : "bg-red-500/10 text-red-700"}`}>
                                {op.op === "insert" ? "(空)" : op.old_text || "(空)"}
                              </pre>
                              <pre className={`overflow-x-auto whitespace-pre-wrap break-words rounded px-2 py-1 font-mono text-[12px] ${op.op === "delete" ? "bg-[rgba(19,34,53,0.04)] text-[var(--text-muted)]" : "bg-emerald-500/10 text-emerald-700"}`}>
                                {op.op === "delete" ? "(空)" : op.new_text || "(空)"}
                              </pre>
                            </div>
                          ) : op.op === "replace" ? (
                            <>
                              <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-red-500/10 px-2 py-0.5 font-mono text-[12px] text-red-700">- {op.old_text || "(空)"}</pre>
                              <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-emerald-500/10 px-2 py-0.5 font-mono text-[12px] text-emerald-700">+ {op.new_text || "(空)"}</pre>
                            </>
                          ) : op.op === "insert" ? (
                            <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-emerald-500/10 px-2 py-0.5 font-mono text-[12px] text-emerald-700">+ {op.new_text || "(空)"}</pre>
                          ) : (
                            <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-red-500/10 px-2 py-0.5 font-mono text-[12px] text-red-700">- {op.old_text || "(空)"}</pre>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-2 text-xs text-[var(--text-muted)]">当前 hunk 仅包含空白改动。</p>
                  )
                ) : null}
              </div>
            );
          })
        )}
      </div>

      <div className="mt-3 flex flex-wrap justify-end gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={onCopy}
          disabled={isApplyingRewrite}
        >
          复制改写
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onCancel}
          disabled={isApplyingRewrite}
        >
          取消
        </Button>
        <Button
          size="sm"
          onClick={onApply}
          disabled={isApplyingRewrite || isSaving}
        >
          {isApplyingRewrite ? "应用中..." : "确认应用"}
        </Button>
      </div>
    </div>
  );
}
