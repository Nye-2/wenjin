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

type KnownResultKind = WorkspaceResultPreview["kind"] | "sandbox";

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
    label: "文档产物",
    shortLabel: "文档",
    groupLabel: "文档产物",
    accent: "#2563eb",
    tint: "rgba(37, 99, 235, 0.08)",
    border: "rgba(37, 99, 235, 0.24)",
    order: 20,
  },
  memory_fact: {
    label: "记忆片段",
    shortLabel: "记忆",
    groupLabel: "记忆片段",
    accent: "#b45309",
    tint: "rgba(217, 119, 6, 0.09)",
    border: "rgba(217, 119, 6, 0.25)",
    order: 30,
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
