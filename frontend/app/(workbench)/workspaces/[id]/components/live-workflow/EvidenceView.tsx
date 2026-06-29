import { useMemo } from "react";
import { Search } from "lucide-react";

import { NodeInspector } from "./NodeInspector";
import { ResultPreviewDetail } from "../result-preview/ResultPreviewDetail";
import { EmptyState, GuidanceNote, ResultKindBadge } from "./shared";
import { styles } from "./styles";
import type { EvidenceFilter, EvidenceItem } from "./types";
import { truncate } from "./utils";

export function EvidenceView({
  items,
  filter,
  query,
  selectedId,
  onFilterChange,
  onQueryChange,
  onSelect,
}: {
  items: EvidenceItem[];
  filter: EvidenceFilter;
  query: string;
  selectedId: string | null;
  onFilterChange: (filter: EvidenceFilter) => void;
  onQueryChange: (query: string) => void;
  onSelect: (id: string) => void;
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
    ["outputs", "结果"],
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
        <div style={{ marginBottom: 12 }}>
          <GuidanceNote>
            证据区只做预览和筛选：文档和资料会随完成运行自动写入，过程摘录和运行细节默认只读。
          </GuidanceNote>
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
                    <span style={styles.readOnlyMark}>只读</span>
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
          <ResultPreviewDetail preview={selected.preview} />
        ) : selected?.source === "node" ? (
          <NodeInspector
            node={{ id: selected.nodeId, type: selected.kind, label: selected.title }}
            state={selected.nodeState}
          />
        ) : (
          <EmptyState title="选择一项内容" detail="这里会显示结果、来源详情或过程摘要。" compact />
        )}
      </aside>
    </div>
  );
}
