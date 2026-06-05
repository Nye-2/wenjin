"use client";

import type { LatexDiffOp, LatexFileChangePreviewResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

interface LatexFileChangeDiffPreviewProps {
  preview: LatexFileChangePreviewResponse;
  maxOps?: number;
  className?: string;
}

function riskFlagLabel(flag: string): string {
  const labels: Record<string, string> = {
    boundary_leak: "越界改写",
    citation_drop: "引用被删",
    label_drop: "标签被删",
    brace_unbalanced: "花括号不平衡",
    math_structure_change: "数学结构变化",
    math_change: "数学相关改动",
    large_change: "改动较大",
    citation_change: "引用改动",
    label_change: "标签改动",
  };
  return labels[flag] || flag;
}

function riskFlagClass(flag: string): string {
  if (["boundary_leak", "citation_drop", "label_drop", "brace_unbalanced"].includes(flag)) {
    return "border-red-500/25 bg-red-500/10 text-red-700";
  }
  if (["math_structure_change", "math_change", "large_change"].includes(flag)) {
    return "border-amber-500/25 bg-amber-500/10 text-amber-800";
  }
  return "border-[var(--wjn-line)] bg-white/80 text-[var(--wjn-text-muted)]";
}

function tokenKindLabel(kind: string): string {
  if (kind === "citation") return "引用";
  if (kind === "label") return "标签";
  if (kind === "math") return "数学";
  if (kind === "env") return "环境";
  if (kind === "latex_cmd") return "命令";
  return "文本";
}

function diffOpLabel(op: LatexDiffOp["op"]): string {
  if (op === "replace") return "替换";
  if (op === "insert") return "新增";
  if (op === "delete") return "删除";
  return "保持";
}

function diffOpTone(op: LatexDiffOp["op"]): string {
  if (op === "insert") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-700";
  }
  if (op === "delete") {
    return "border-red-500/20 bg-red-500/10 text-red-700";
  }
  if (op === "replace") {
    return "border-amber-500/20 bg-amber-500/10 text-amber-800";
  }
  return "border-[var(--wjn-line)] bg-white/80 text-[var(--wjn-text-muted)]";
}

function isWhitespaceOnlyDiffOp(op: LatexDiffOp): boolean {
  const oldCompact = op.old_text.replace(/\s+/g, "");
  const newCompact = op.new_text.replace(/\s+/g, "");
  return oldCompact === newCompact && op.old_text !== op.new_text;
}

function collectChangedOps(preview: LatexFileChangePreviewResponse): LatexDiffOp[] {
  return preview.diff.hunks.flatMap((hunk) => hunk.ops.filter((op) => op.op !== "equal"));
}

export function LatexFileChangeDiffPreview({
  preview,
  maxOps = 6,
  className,
}: LatexFileChangeDiffPreviewProps) {
  const changedOps = collectChangedOps(preview);
  const visibleOps = changedOps.slice(0, maxOps);
  const remainingOps = Math.max(0, changedOps.length - visibleOps.length);

  return (
    <div
      className={cn(
        "rounded-lg border border-[var(--wjn-line)] bg-white/80 p-2",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--wjn-text-muted)]">
        <span>token {preview.diff.stats.tokens_changed}</span>
        <span>+{preview.diff.stats.chars_added}</span>
        <span>-{preview.diff.stats.chars_deleted}</span>
        <span>{preview.diff.hunks.length} hunks</span>
      </div>
      {preview.diff.risk_flags.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {preview.diff.risk_flags.map((flag) => (
            <span
              key={flag}
              className={cn("rounded-full border px-2 py-0.5 text-[10px]", riskFlagClass(flag))}
            >
              {riskFlagLabel(flag)}
            </span>
          ))}
        </div>
      ) : null}
      <div className="mt-2 max-h-48 space-y-1.5 overflow-auto">
        {visibleOps.length > 0 ? (
          visibleOps.map((op, index) => (
            <div
              key={`${op.old_start}-${op.old_end}-${op.new_start}-${op.new_end}-${index}`}
              className="rounded-md border border-[var(--wjn-line)] bg-[rgba(19,34,53,0.03)] p-2"
            >
              <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[10px] text-[var(--wjn-text-muted)]">
                <span className={cn("rounded border px-1.5 py-0.5", diffOpTone(op.op))}>
                  {diffOpLabel(op.op)}
                </span>
                <span className="rounded border border-[var(--wjn-line)] bg-white px-1.5 py-0.5">
                  {tokenKindLabel(op.token_kind)}
                </span>
                {isWhitespaceOnlyDiffOp(op) ? (
                  <span className="rounded border border-[var(--wjn-line)] bg-white px-1.5 py-0.5">
                    仅空白
                  </span>
                ) : null}
              </div>
              {op.op === "replace" ? (
                <div className="space-y-1">
                  <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-red-500/10 px-2 py-1 font-mono text-[11px] leading-5 text-red-700">
                    - {op.old_text || "(空)"}
                  </pre>
                  <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-emerald-500/10 px-2 py-1 font-mono text-[11px] leading-5 text-emerald-700">
                    + {op.new_text || "(空)"}
                  </pre>
                </div>
              ) : op.op === "insert" ? (
                <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-emerald-500/10 px-2 py-1 font-mono text-[11px] leading-5 text-emerald-700">
                  + {op.new_text || "(空)"}
                </pre>
              ) : (
                <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-red-500/10 px-2 py-1 font-mono text-[11px] leading-5 text-red-700">
                  - {op.old_text || "(空)"}
                </pre>
              )}
            </div>
          ))
        ) : (
          <p className="text-xs text-[var(--wjn-text-muted)]">未检测到文本差异。</p>
        )}
      </div>
      {remainingOps > 0 ? (
        <p className="mt-2 text-[11px] text-[var(--wjn-text-muted)]">
          另有 {remainingOps} 条 diff 操作，请在 Prism 中查看完整上下文。
        </p>
      ) : null}
    </div>
  );
}
