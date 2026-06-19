import { useMemo } from "react";
import { Search } from "lucide-react";

import type { WorkbenchDraftEdit } from "@/stores/workbench-layout-store";

import { NodeInspector } from "./NodeInspector";
import { ResultEditor } from "./ResultEditor";
import { EmptyState, ResultKindBadge } from "./shared";
import { styles } from "./styles";
import type { EvidenceFilter, EvidenceItem } from "./types";
import { truncate } from "./utils";

export function EvidenceView({
  items,
  filter,
  query,
  selectedId,
  checkedIds,
  draftEdits,
  disabled,
  onFilterChange,
  onQueryChange,
  onSelect,
  onToggleChecked,
  onPatchDraft,
  onSetDraft,
}: {
  items: EvidenceItem[];
  filter: EvidenceFilter;
  query: string;
  selectedId: string | null;
  checkedIds: Set<string>;
  draftEdits: Record<string, WorkbenchDraftEdit>;
  disabled: boolean;
  onFilterChange: (filter: EvidenceFilter) => void;
  onQueryChange: (query: string) => void;
  onSelect: (id: string) => void;
  onToggleChecked: (id: string) => void;
  onPatchDraft: (outputId: string, field: string, value: unknown) => void;
  onSetDraft: (outputId: string, edit: WorkbenchDraftEdit | null) => void;
}) {
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((item) => {
      if (filter === "outputs" && item.source !== "output") return false;
      if (filter === "nodes" && item.source !== "node") return false;
      if (filter === "sandbox" && !item.summary.toLowerCase().includes("sandbox") && item.kind !== "sandbox") return false;
      if (!q) return true;
      return `${item.title} ${item.kind} ${item.summary}`.toLowerCase().includes(q);
    });
  }, [filter, items, query]);
  const experimentCount = items.filter(
    (item) =>
      item.kind === "sandbox" ||
      item.summary.toLowerCase().includes("sandbox") ||
      item.summary.includes("实验"),
  ).length;
  const selected =
    filtered.find((item) => item.id === selectedId) ??
    filtered[0] ??
    null;
  const filterOptions: Array<[EvidenceFilter, string]> = [
    ["all", "全部"],
    ["outputs", "候选结果"],
    ["nodes", "过程"],
    ...(experimentCount > 0 ? ([["sandbox", "实验记录"]] as Array<[EvidenceFilter, string]>) : []),
  ];

  return (
    <div style={styles.evidenceGrid}>
      <section style={styles.section}>
        <div style={styles.toolbar}>
          <div style={styles.searchBox}>
            <Search size={15} />
            <input
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="搜索标题、作者、来源或摘要"
              style={styles.searchInput}
            />
          </div>
          <div style={styles.segmented}>
            {filterOptions.map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => onFilterChange(key as EvidenceFilter)}
                style={{
                  ...styles.segmentButton,
                  ...(filter === key ? styles.segmentButtonActive : null),
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {filtered.length > 0 ? (
          <div style={styles.evidenceList}>
            {filtered.map((item) => {
              const isSelected = selected?.id === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onSelect(item.id)}
                  style={{
                    ...styles.evidenceListItem,
                    ...(isSelected ? styles.evidenceListItemActive : null),
                  }}
                >
                  <span style={styles.evidenceListCheck}>
                    {item.source === "output" ? (
                      <input
                        type="checkbox"
                        aria-label={`选择${item.title}`}
                        checked={checkedIds.has(item.preview.id)}
                        disabled={disabled}
                        onChange={(event) => {
                          event.stopPropagation();
                          onToggleChecked(item.preview.id);
                        }}
                        onClick={(event) => event.stopPropagation()}
                        style={styles.checkbox}
                      />
                    ) : (
                      <span style={styles.readOnlyMark}>只读</span>
                    )}
                  </span>
                  <span style={styles.evidenceListMain}>
                    <span style={styles.evidenceListTitle}>{item.title}</span>
                    <span style={styles.evidenceListSummary}>{truncate(item.summary, 160)}</span>
                  </span>
                  <span style={styles.evidenceListKind}>
                    <ResultKindBadge kind={item.kind} />
                  </span>
                </button>
              );
            })}
          </div>
        ) : (
          <EmptyState title="没有匹配内容" detail="调整搜索或筛选条件后再查看。" compact />
        )}
      </section>

      <aside style={styles.editorAside}>
        {selected?.source === "output" ? (
          <ResultEditor
            preview={selected.preview}
            draft={draftEdits[selected.preview.id]}
            disabled={disabled}
            onPatchDraft={onPatchDraft}
            onSetDraft={onSetDraft}
          />
        ) : selected?.source === "node" ? (
          <NodeInspector
            node={{ id: selected.nodeId, type: selected.kind, label: selected.title }}
            state={selected.nodeState}
          />
        ) : (
          <EmptyState title="选择一项内容" detail="这里会显示候选结果、来源详情或过程摘要。" compact />
        )}
      </aside>
    </div>
  );
}
