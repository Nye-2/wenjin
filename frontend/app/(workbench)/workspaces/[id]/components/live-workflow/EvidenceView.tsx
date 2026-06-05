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
  const selected =
    filtered.find((item) => item.id === selectedId) ??
    filtered[0] ??
    null;

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
            {[
              ["all", "全部"],
              ["outputs", "候选结果"],
              ["nodes", "过程记录"],
              ["sandbox", "Sandbox"],
            ].map(([key, label]) => (
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
          <div style={styles.evidenceTableWrap}>
            <table style={styles.evidenceTable}>
              <thead>
                <tr>
                  <th style={styles.th}>包含</th>
                  <th style={styles.th}>类型</th>
                  <th style={styles.th}>标题 / 来源</th>
                  <th style={styles.th}>摘要</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => {
                  const isSelected = selected?.id === item.id;
                  return (
                    <tr
                      key={item.id}
                      onClick={() => onSelect(item.id)}
                      style={{
                        ...styles.tr,
                        ...(isSelected ? styles.trSelected : null),
                      }}
                    >
                      <td style={styles.td}>
                        {item.source === "output" ? (
                          <input
                            type="checkbox"
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
                      </td>
                      <td style={styles.td}>
                        <ResultKindBadge kind={item.kind} />
                      </td>
                      <td style={styles.tdStrong}>{item.title}</td>
                      <td style={styles.tdMuted}>{truncate(item.summary, 140)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="没有匹配证据" detail="调整搜索或过滤条件后再查看。" compact />
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
          <EmptyState title="选择证据项" detail="可在这里编辑候选结果字段，或查看过程摘要。" compact />
        )}
      </aside>
    </div>
  );
}
