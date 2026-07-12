export type ReviewCopyRisk = "low" | "medium" | "high" | "critical";
export type ReviewCopyApplyState =
  | "draft_applied"
  | "staged"
  | "accepted"
  | "rejected"
  | "blocked"
  | "undone";

type ReviewIssueCopy = {
  title: string;
  summary: string;
};

const REVIEW_ISSUE_PATTERNS: Array<{
  test: RegExp;
  copy: ReviewIssueCopy;
}> = [
  {
    test: /No previewable Review Packet item was produced/i,
    copy: {
      title: "需要补充可查看的复核材料",
      summary:
        "这次运行没有生成可预览的复核材料。建议查看运行详情，或让问津补充一份可复核摘要。",
    },
  },
  {
    test: /No claim-bearing Review Packet item was produced/i,
    copy: {
      title: "需要补充论断与证据对应",
      summary:
        "这次运行没有给出“论断-证据”的对应关系。涉及论文论断前，需要补齐引用或证据说明。",
    },
  },
  {
    test: /unsupported claim/i,
    copy: {
      title: "有论断还缺少证据支撑",
      summary: "这项内容还没有足够证据支撑。建议补充来源后再保存。",
    },
  },
  {
    test: /citation evidence requires manual confirmation/i,
    copy: {
      title: "引用或证据需要确认",
      summary: "这项内容涉及引用或证据，需要你看过来源后再保存。",
    },
  },
  {
    test: /document draft changes require review/i,
    copy: {
      title: "文档草稿需要复核",
      summary: "这项内容会写入文档草稿，建议先看一眼再保存。",
    },
  },
  {
    test: /workspace write policy changes require review/i,
    copy: {
      title: "写入策略需要确认",
      summary: "这项内容会影响工作区写入方式，需要确认后再继续。",
    },
  },
];

const TECHNICAL_REASON_PATTERNS: Array<{
  test: RegExp;
  label: string | null;
}> = [
  {
    test: /No previewable Review Packet item was produced/i,
    label: "没有生成可预览的复核材料。",
  },
  {
    test: /No claim-bearing Review Packet item was produced/i,
    label: "没有给出“论断-证据”的对应关系。",
  },
  {
    test: /review warning requires manual resolution/i,
    label: "需要你确认后再继续保存。",
  },
  {
    test: /item touches claims, citations, evidence, or trust state/i,
    label: "涉及论断、引用、证据或可信状态。",
  },
  {
    test: /item is unchecked by default/i,
    label: "默认不选中，避免误保存。",
  },
  {
    test: /cannot be committed/i,
    label: "当前不会写入工作区。",
  },
  {
    test: /citation evidence requires manual confirmation/i,
    label: "引用或证据需要人工确认。",
  },
  {
    test: /document draft changes require review/i,
    label: "文档草稿需要先复核。",
  },
  {
    test: /workspace write policy changes require review/i,
    label: "写入策略需要确认。",
  },
  {
    test: /unsupported claim/i,
    label: "有论断还缺少证据支撑。",
  },
  {
    test: /^(high|medium|low|critical|blocked|staged)$/i,
    label: null,
  },
];

export function reviewRiskLabel(value: ReviewCopyRisk): string {
  const labels: Record<ReviewCopyRisk, string> = {
    low: "可保存",
    medium: "建议复核",
    high: "需人工确认",
    critical: "暂不建议保存",
  };
  return labels[value];
}

export function reviewApplyStateLabel(value: ReviewCopyApplyState): string {
  const labels: Record<ReviewCopyApplyState, string> = {
    draft_applied: "草稿已应用",
    staged: "待复核",
    accepted: "已确认",
    rejected: "暂不保存",
    blocked: "需补充",
    undone: "已撤回",
  };
  return labels[value];
}

export function reviewIssueTitle(options: {
  title?: string | null;
  summary?: string | null;
  reasons?: string[];
  fallback?: string;
}): string {
  const rawTitle = cleanText(options.title);
  const issueCopy = findReviewIssueCopy([
    options.summary,
    rawTitle,
    ...(options.reasons ?? []),
  ]);
  if (
    issueCopy &&
    (!rawTitle ||
      /科研质量门未通过|quality gate|review packet|claim-bearing|previewable/i.test(
        rawTitle,
      ))
  ) {
    return issueCopy.title;
  }
  return rawTitle ?? issueCopy?.title ?? options.fallback ?? "需要复核的内容";
}

export function reviewIssueSummary(value: unknown): string | null {
  const text = cleanText(value);
  if (!text) {
    return null;
  }
  const issueCopy = findReviewIssueCopy([text]);
  if (issueCopy) {
    return issueCopy.summary;
  }
  return text
    .replace(/quality gate/gi, "复核检查")
    .replace(/Review Packet/gi, "复核材料")
    .replace(/blocked/gi, "需补充")
    .replace(/high risk/gi, "需人工确认");
}

export function reviewReasonLabels(reasons: string[]): string[] {
  const labels: string[] = [];
  const seen = new Set<string>();
  for (const reason of reasons) {
    const label = reviewReasonLabel(reason);
    if (!label || seen.has(label)) {
      continue;
    }
    labels.push(label);
    seen.add(label);
  }
  return labels;
}

export function reviewPacketBadgeLabel(
  kind: string,
  reviewState: "supported" | "needs_confirmation" | "blocker",
): string {
  if (reviewState === "blocker") {
    return "需补充";
  }
  if (reviewState === "needs_confirmation") {
    return "需确认";
  }
  if (kind === "warning") {
    return "提醒";
  }
  return "";
}

function reviewReasonLabel(reason: string): string | null {
  const text = cleanText(reason);
  if (!text) {
    return null;
  }
  for (const pattern of TECHNICAL_REASON_PATTERNS) {
    if (pattern.test.test(text)) {
      return pattern.label;
    }
  }
  return reviewIssueSummary(text);
}

function findReviewIssueCopy(values: Array<unknown>): ReviewIssueCopy | null {
  for (const value of values) {
    const text = cleanText(value);
    if (!text) {
      continue;
    }
    const match = REVIEW_ISSUE_PATTERNS.find((pattern) =>
      pattern.test.test(text),
    );
    if (match) {
      return match.copy;
    }
  }
  return null;
}

function cleanText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
