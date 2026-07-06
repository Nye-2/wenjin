import type { WorkspaceResultPreview } from "./workspace-result-preview";

export interface WorkspaceResultKindMeta {
  label: string;
  shortLabel: string;
  groupLabel: string;
  accent: string;
  tint: string;
  border: string;
  order: number;
}

type KnownResultKind =
  | Exclude<WorkspaceResultPreview["kind"], "memory_fact">
  | "sandbox";
const HIDDEN_RESULT_KINDS = new Set<string>(["memory_fact"]);

const KIND_META: Record<KnownResultKind, WorkspaceResultKindMeta> = {
  library_item: {
    label: "文献资料",
    shortLabel: "文献",
    groupLabel: "文献资料",
    accent: "#0f766e",
    tint: "rgba(13, 148, 136, 0.08)",
    border: "rgba(13, 148, 136, 0.24)",
    order: 10,
  },
  document: {
    label: "文档文件",
    shortLabel: "文件",
    groupLabel: "文档文件",
    accent: "#2563eb",
    tint: "rgba(37, 99, 235, 0.08)",
    border: "rgba(37, 99, 235, 0.24)",
    order: 20,
  },
  figure: {
    label: "图表文件",
    shortLabel: "图表",
    groupLabel: "图表文件",
    accent: "#7c3aed",
    tint: "rgba(124, 58, 237, 0.08)",
    border: "rgba(124, 58, 237, 0.22)",
    order: 22,
  },
  decision: {
    label: "决策记录",
    shortLabel: "决策",
    groupLabel: "决策记录",
    accent: "var(--wjn-blue)",
    tint: "var(--wjn-accent-soft)",
    border: "var(--wjn-accent-line)",
    order: 40,
  },
  task: {
    label: "任务项",
    shortLabel: "任务",
    groupLabel: "任务项",
    accent: "#475569",
    tint: "rgba(71, 85, 105, 0.08)",
    border: "rgba(71, 85, 105, 0.2)",
    order: 50,
  },
  reference: {
    label: "证据来源",
    shortLabel: "来源",
    groupLabel: "证据来源",
    accent: "#047857",
    tint: "rgba(4, 120, 87, 0.08)",
    border: "rgba(4, 120, 87, 0.22)",
    order: 55,
  },
  dataset: {
    label: "数据材料",
    shortLabel: "数据",
    groupLabel: "数据材料",
    accent: "#0369a1",
    tint: "rgba(3, 105, 161, 0.08)",
    border: "rgba(3, 105, 161, 0.22)",
    order: 56,
  },
  artifact: {
    label: "实验结果",
    shortLabel: "实验",
    groupLabel: "实验结果",
    accent: "#6d28d9",
    tint: "rgba(109, 40, 217, 0.08)",
    border: "rgba(109, 40, 217, 0.22)",
    order: 57,
  },
  prism_change: {
    label: "改稿建议",
    shortLabel: "改稿",
    groupLabel: "改稿建议",
    accent: "#1d4ed8",
    tint: "rgba(29, 78, 216, 0.08)",
    border: "rgba(29, 78, 216, 0.22)",
    order: 58,
  },
  warning: {
    label: "风险提示",
    shortLabel: "风险",
    groupLabel: "风险提示",
    accent: "#b45309",
    tint: "rgba(217, 119, 6, 0.1)",
    border: "rgba(217, 119, 6, 0.24)",
    order: 59,
  },
  sandbox: {
    label: "实验记录",
    shortLabel: "实验",
    groupLabel: "实验记录",
    accent: "var(--wjn-text-secondary)",
    tint: "var(--wjn-surface-subtle)",
    border: "var(--wjn-line)",
    order: 60,
  },
};

const FALLBACK_META: WorkspaceResultKindMeta = {
  label: "过程记录",
  shortLabel: "输出",
  groupLabel: "过程记录",
  accent: "#64748b",
  tint: "rgba(100, 116, 139, 0.08)",
  border: "rgba(100, 116, 139, 0.2)",
  order: 900,
};

export function getWorkspaceResultKindMeta(
  kind: string,
): WorkspaceResultKindMeta {
  return KIND_META[kind as KnownResultKind] ?? FALLBACK_META;
}

export function isWorkspaceResultKindVisibleToUser(kind: string): boolean {
  return !HIDDEN_RESULT_KINDS.has(kind);
}

export function filterVisibleWorkspaceResultItems<T extends { kind: string }>(
  items: T[],
): T[] {
  return items.filter((item) => isWorkspaceResultKindVisibleToUser(item.kind));
}

export function groupWorkspaceResultPreviews<T extends { kind: string }>(
  items: T[],
): Array<{
  kind: string;
  meta: WorkspaceResultKindMeta;
  items: T[];
}> {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const existing = groups.get(item.kind);
    if (existing) {
      existing.push(item);
    } else {
      groups.set(item.kind, [item]);
    }
  }

  return Array.from(groups.entries())
    .map(([kind, groupItems]) => ({
      kind,
      meta: getWorkspaceResultKindMeta(kind),
      items: groupItems,
    }))
    .sort((a, b) => {
      const orderDelta = a.meta.order - b.meta.order;
      return orderDelta !== 0 ? orderDelta : a.kind.localeCompare(b.kind);
    });
}
