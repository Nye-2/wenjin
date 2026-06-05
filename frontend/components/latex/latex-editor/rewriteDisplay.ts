export const STALE_REWRITE_ERROR_CODES = new Set([
  "invalid_candidate_signature",
  "base_file_hash_mismatch",
  "base_range_hash_mismatch",
  "target_range_out_of_bounds",
]);

export const STRUCTURE_REWRITE_ERROR_CODES = new Set([
  "boundary_leak",
  "citation_drop",
  "label_drop",
  "ref_drop",
  "brace_unbalanced",
  "environment_unbalanced",
  "math_delimiter_unbalanced",
]);

export function rewriteProfileLabel(profile: "balanced" | "conservative" | "aggressive"): string {
  if (profile === "conservative") return "保守";
  if (profile === "aggressive") return "激进";
  return "平衡";
}

export function riskLevelLabel(level: "low" | "medium" | "high"): string {
  if (level === "high") return "高风险";
  if (level === "medium") return "中风险";
  return "低风险";
}

export function riskLevelClass(level: "low" | "medium" | "high"): string {
  if (level === "high") return "border-red-500/25 bg-red-500/10 text-red-700";
  if (level === "medium") return "border-amber-500/25 bg-amber-500/10 text-amber-800";
  return "border-emerald-500/25 bg-emerald-500/10 text-emerald-700";
}

export function riskFlagClass(flag: string): string {
  if (["boundary_leak", "citation_drop", "label_drop", "brace_unbalanced"].includes(flag)) {
    return "border-red-500/25 bg-red-500/10 text-red-700";
  }
  if (["math_structure_change", "math_change", "large_change"].includes(flag)) {
    return "border-amber-500/25 bg-amber-500/10 text-amber-800";
  }
  return "border-[var(--wjn-line)] bg-white/80 text-[var(--wjn-text-muted)]";
}

export function riskFlagLabel(flag: string): string {
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

export function tokenKindLabel(kind: string): string {
  if (kind === "citation") return "引用";
  if (kind === "label") return "标签";
  if (kind === "math") return "数学";
  if (kind === "env") return "环境";
  if (kind === "latex_cmd") return "命令";
  return "文本";
}

export function diffOpLabel(op: "equal" | "insert" | "delete" | "replace"): string {
  if (op === "replace") return "替换";
  if (op === "insert") return "新增";
  if (op === "delete") return "删除";
  return "保持";
}

export function isWhitespaceOnlyDiffOp(op: { old_text: string; new_text: string }): boolean {
  const oldCompact = op.old_text.replace(/\s+/g, "");
  const newCompact = op.new_text.replace(/\s+/g, "");
  return oldCompact === newCompact && op.old_text !== op.new_text;
}
