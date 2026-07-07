"use client";

import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  FileDiff,
  RotateCcw,
  ShieldAlert,
  X,
} from "lucide-react";

import type {
  ChangeRisk,
  ChangeSetGroup,
  RunViewChangeSet,
  RunViewChangeUnit,
} from "@/lib/change-set-view";
import {
  isChangeUnitPendingReview,
  isChangeUnitReviewActionable,
} from "@/lib/change-set-view";

import { EmptyState, GuidanceNote } from "../live-workflow/shared";
import { styles } from "../live-workflow/styles";
import { WritebackStatus, type RunWritebackStatus } from "../live-workflow/RunView";

export type ChangeSetReviewAction = "accept" | "reject" | "undo";

export interface ChangeSetReviewActionState {
  executionId: string | null;
  action: ChangeSetReviewAction | null;
  unitIds: string[];
  error: string | null;
}

interface ChangeSetReviewPanelProps {
  changeSet: RunViewChangeSet;
  pendingReviewCount: number;
  actionState?: ChangeSetReviewActionState;
  writeback?: RunWritebackStatus;
  onAcceptUnits: (unitIds: string[]) => void;
  onRejectUnits: (unitIds: string[]) => void;
  onUndoUnits: (unitIds: string[]) => void;
}

const GROUP_ORDER: Array<{ key: ChangeSetGroup; label: string; detail: string }> = [
  {
    key: "needs_confirmation",
    label: "待复核",
    detail: "这些变更需要复核后，才会进入保存流程。",
  },
  {
    key: "blocked",
    label: "已阻断",
    detail: "高风险变更，需要逐条检查或重新生成。",
  },
  {
    key: "accepted",
    label: "已确认",
    detail: "这些变更已确认，下一步可保存到工作区。",
  },
  {
    key: "draft_applied",
    label: "草稿已应用",
    detail: "低风险草稿已自动应用，此处只读查看。",
  },
  {
    key: "rejected",
    label: "已拒绝",
    detail: "这些变更不会写入本次结果。",
  },
  {
    key: "undone",
    label: "已撤销",
    detail: "之前的复核决定已撤回。",
  },
];

export function ChangeSetReviewPanel({
  changeSet,
  pendingReviewCount,
  actionState,
  writeback,
  onAcceptUnits,
  onRejectUnits,
  onUndoUnits,
}: ChangeSetReviewPanelProps) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [expandedIds, setExpandedIds] = useState<string[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  const selectedIdSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const expandedIdSet = useMemo(() => new Set(expandedIds), [expandedIds]);
  const selectedUnits = useMemo(
    () => changeSet.units.filter((unit) => selectedIdSet.has(unit.id)),
    [changeSet.units, selectedIdSet],
  );
  const pendingUnits = useMemo(
    () => changeSet.units.filter(isChangeUnitPendingReview),
    [changeSet.units],
  );
  const bulkSelectableUnits = useMemo(
    () => changeSet.units.filter(isBulkSelectableChangeUnit),
    [changeSet.units],
  );
  const activeUnit =
    changeSet.units.find((unit) => unit.id === activeId) ??
    pendingUnits[0] ??
    changeSet.units[0] ??
    null;
  const busy =
    actionState?.executionId === changeSet.executionId && actionState.action !== null;
  const reviewStatusMessage = reviewActionStatusMessage(
    actionState,
    changeSet.executionId,
  );

  useEffect(() => {
    const firstPending = changeSet.units.find(isChangeUnitPendingReview);
    setSelectedIds([]);
    setExpandedIds(firstPending ? [firstPending.id] : []);
    setActiveId(firstPending?.id ?? changeSet.units[0]?.id ?? null);
  }, [changeSet.executionId]);

  function toggleSelected(unitId: string) {
    const unit = changeSet.units.find((item) => item.id === unitId);
    if (!unit || !isChangeUnitReviewActionable(unit)) {
      return;
    }
    setSelectedIds((current) =>
      current.includes(unitId)
        ? current.filter((id) => id !== unitId)
        : [...current, unitId],
    );
  }

  function toggleExpanded(unitId: string) {
    setExpandedIds((current) =>
      current.includes(unitId)
        ? current.filter((id) => id !== unitId)
        : [...current, unitId],
    );
  }

  function selectPendingUnits() {
    setSelectedIds(bulkSelectableUnits.map((unit) => unit.id));
  }

  function clearSelection() {
    setSelectedIds([]);
  }

  function runAction(action: ChangeSetReviewAction, ids: string[]) {
    if (ids.length === 0 || busy) {
      return;
    }
    if (action === "accept") {
      onAcceptUnits(ids);
    } else if (action === "reject") {
      onRejectUnits(ids);
    } else {
      onUndoUnits(ids);
    }
  }

  const selectedCount = selectedUnits.length;
  const actionIds = selectedUnits
    .filter(isChangeUnitReviewActionable)
    .map((unit) => unit.id);
  const undoActionIds = selectedUnits
    .filter(isUndoableReviewDecision)
    .map((unit) => unit.id);

  return (
    <div style={styles.reviewGrid}>
      <section style={styles.reviewInbox} aria-label="变更复核队列">
        <div style={styles.sectionHeaderCompact}>
          <div>
            <h2 style={{ ...styles.sectionTitle, margin: 0 }}>复核与保存</h2>
            <div style={styles.sectionSubtitle}>
              {pendingReviewCount} 项变更待复核。
            </div>
          </div>
        </div>
        <GuidanceNote>
          先逐条复核变更；确认后再保存到工作区。
        </GuidanceNote>

        <div style={panelStyles.summaryGrid} aria-label="Change set summary">
          <SummaryCell label="待复核" value={changeSet.counts.needs_confirmation} />
          <SummaryCell label="已阻断" value={changeSet.counts.blocked} tone="risk" />
          <SummaryCell label="已确认" value={changeSet.counts.accepted} tone="success" />
          <SummaryCell label="草稿" value={changeSet.counts.draft_applied} />
        </div>

        <div style={panelStyles.toolbar}>
          <button
            type="button"
            onClick={selectPendingUnits}
            disabled={bulkSelectableUnits.length === 0 || busy}
            style={styles.ghostButton}
            aria-label="全选低/中风险待复核变更"
          >
            全选低/中风险
          </button>
          <button
            type="button"
            onClick={clearSelection}
            disabled={actionIds.length === 0 || busy}
            style={styles.ghostButton}
            aria-label="清除已选变更"
          >
            清除
          </button>
          <span style={panelStyles.selectionCount}>已选 {selectedCount} 项</span>
        </div>

        <div style={panelStyles.actionBar}>
          <button
            type="button"
            onClick={() => runAction("accept", actionIds)}
            disabled={actionIds.length === 0 || busy}
            style={styles.secondaryButton}
            aria-label="确认选中变更"
          >
            <Check size={14} />
            {busy && actionState?.action === "accept" ? "确认中..." : "确认选中"}
          </button>
          <button
            type="button"
            onClick={() => runAction("reject", actionIds)}
            disabled={actionIds.length === 0 || busy}
            style={styles.secondaryButton}
            aria-label="拒绝选中变更"
          >
            <X size={14} />
            {busy && actionState?.action === "reject" ? "拒绝中..." : "拒绝选中"}
          </button>
          <button
            type="button"
            onClick={() => runAction("undo", undoActionIds)}
            disabled={undoActionIds.length === 0 || busy}
            style={styles.secondaryButton}
            aria-label="撤销选中复核决定"
          >
            <RotateCcw size={14} />
            {busy && actionState?.action === "undo" ? "撤销中..." : "撤销决定"}
          </button>
        </div>

        {reviewStatusMessage ? (
          <div
            role="status"
            aria-label="复核状态"
            aria-live="polite"
            aria-atomic="true"
            style={actionState?.error ? styles.commitError : visuallyHiddenStyle}
          >
            {reviewStatusMessage}
          </div>
        ) : null}

        <div style={panelStyles.groupStack}>
          {GROUP_ORDER.map((group) => {
            const units = changeSet.units.filter((unit) => unit.group === group.key);
            if (units.length === 0) {
              return null;
            }
            return (
              <section key={group.key} style={panelStyles.group} aria-label={group.label}>
                <div style={styles.previewGroupHeader}>
                  <div>
                    <div style={styles.previewGroupTitle}>{group.label}</div>
                    <div style={panelStyles.groupDetail}>{group.detail}</div>
                  </div>
                  <span style={groupCountStyle(group.key)}>{units.length}</span>
                </div>
                <div style={panelStyles.unitList}>
                  {units.map((unit) => (
                    <ChangeUnitRow
                      key={unit.id}
                      unit={unit}
                      selected={selectedIdSet.has(unit.id)}
                      expanded={expandedIdSet.has(unit.id)}
                      active={activeUnit?.id === unit.id}
                      disabled={busy}
                      selectionDisabled={!isChangeUnitReviewActionable(unit)}
                      onSelect={() => toggleSelected(unit.id)}
                      onActivate={() => setActiveId(unit.id)}
                      onToggleExpanded={() => toggleExpanded(unit.id)}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      </section>

      <aside style={styles.reviewDetail}>
        {activeUnit ? (
          <ChangeUnitDetail
            unit={activeUnit}
            busy={busy}
            writeback={writeback}
            onAccept={() => runAction("accept", [activeUnit.id])}
            onReject={() => runAction("reject", [activeUnit.id])}
            onUndo={() => runAction("undo", [activeUnit.id])}
          />
        ) : (
          <EmptyState
            title="未选择变更"
            detail="选择一项变更，查看目标、风险和来源依据。"
            compact
          />
        )}
      </aside>
    </div>
  );
}

function SummaryCell({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number;
  tone?: "default" | "risk" | "success";
}) {
  const color =
    tone === "risk"
      ? "var(--wjn-error)"
      : tone === "success"
        ? "var(--wjn-success)"
        : "var(--wjn-text)";
  return (
    <div style={panelStyles.summaryCell}>
      <div style={{ ...panelStyles.summaryValue, color }}>{value}</div>
      <div style={panelStyles.summaryLabel}>{label}</div>
    </div>
  );
}

function ChangeUnitRow({
  unit,
  selected,
  expanded,
  active,
  disabled,
  selectionDisabled,
  onSelect,
  onActivate,
  onToggleExpanded,
}: {
  unit: RunViewChangeUnit;
  selected: boolean;
  expanded: boolean;
  active: boolean;
  disabled: boolean;
  selectionDisabled: boolean;
  onSelect: () => void;
  onActivate: () => void;
  onToggleExpanded: () => void;
}) {
  return (
    <div
      style={{
        ...panelStyles.unitRow,
        ...(active ? panelStyles.unitRowActive : null),
      }}
    >
      <input
        type="checkbox"
        checked={selected}
        disabled={disabled || selectionDisabled}
        onChange={onSelect}
        aria-label={
          selectionDisabled
            ? `${unit.title} 已阻断或不可批量选择`
            : `选择变更 ${unit.title}`
        }
        style={panelStyles.checkbox}
      />
      <button
        type="button"
        onClick={onActivate}
        disabled={disabled}
        style={panelStyles.unitMainButton}
        aria-label={`查看变更详情 ${unit.title}`}
      >
        <span style={panelStyles.unitTitleLine}>
          <span style={panelStyles.unitTitle}>{unit.title}</span>
          {unit.requires_confirmation ? (
            <ShieldAlert size={13} color="var(--wjn-risk-medium)" />
          ) : null}
        </span>
        <span style={panelStyles.unitSubtitle}>{unit.subtitle}</span>
        <span style={panelStyles.badgeLine}>
          <span style={riskBadgeStyle(unit.risk)}>{unit.riskLabel}</span>
          <span style={stateBadgeStyle(unit.state)}>{unit.stateLabel}</span>
        </span>
      </button>
      <button
        type="button"
        onClick={onToggleExpanded}
        disabled={disabled}
        aria-label={`${expanded ? "收起" : "展开"} ${unit.title}`}
        style={panelStyles.expandButton}
      >
        {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
      </button>
      {expanded ? (
        <div style={panelStyles.inlineDiff}>
          <div style={panelStyles.inlineDiffHeader}>
            <FileDiff size={13} />
            变更预览
          </div>
          <div style={panelStyles.inlineDiffText}>{shortDiffSummary(unit)}</div>
        </div>
      ) : null}
    </div>
  );
}

function ChangeUnitDetail({
  unit,
  busy,
  writeback,
  onAccept,
  onReject,
  onUndo,
}: {
  unit: RunViewChangeUnit;
  busy: boolean;
  writeback?: RunWritebackStatus;
  onAccept: () => void;
  onReject: () => void;
  onUndo: () => void;
}) {
  const readOnlyApplied = !isChangeUnitReviewActionable(unit);
  const undoable = isUndoableReviewDecision(unit);
  return (
    <>
      <section style={panelStyles.detailPanel} aria-label="选中变更详情">
        <div style={panelStyles.detailHeader}>
          <div>
            <div style={panelStyles.detailEyebrow}>
              {changeTargetEyebrow(unit)}
            </div>
            <h3 style={panelStyles.detailTitle}>{unit.title}</h3>
            <div style={panelStyles.detailSubtitle}>{unit.subtitle}</div>
          </div>
          <span style={riskBadgeStyle(unit.risk)}>{unit.riskLabel}</span>
        </div>

        <div style={panelStyles.detailActions}>
          <button
            type="button"
            onClick={onAccept}
            disabled={busy || readOnlyApplied}
            style={styles.secondaryButton}
            aria-label={`确认 ${unit.title}`}
          >
            <Check size={14} />
            确认
          </button>
          <button
            type="button"
            onClick={onReject}
            disabled={busy || readOnlyApplied}
            style={styles.secondaryButton}
            aria-label={`拒绝 ${unit.title}`}
          >
            <X size={14} />
            拒绝
          </button>
          <button
            type="button"
            onClick={onUndo}
            disabled={busy || !undoable}
            style={styles.secondaryButton}
            aria-label={`撤销 ${unit.title}`}
          >
            <RotateCcw size={14} />
            撤销
          </button>
        </div>

        {readOnlyApplied ? (
          <div style={panelStyles.readOnlyNotice}>
            这项变更已自动应用为草稿。你可以在这里检查，但暂不能从复核面板直接回滚。
          </div>
        ) : null}

        <div style={panelStyles.metadataGrid}>
          <MetadataItem label="状态" value={unit.stateLabel} />
          <MetadataItem label="复核建议" value={reviewActionDescription(unit)} />
          <MetadataItem label="影响位置" value={changeTargetDescription(unit)} />
          <MetadataItem label="写入方式" value={commitRouteDescription(unit)} />
        </div>

        {unit.risk_reasons.length > 0 ? (
          <div style={panelStyles.reasonBlock}>
            <div style={panelStyles.blockTitle}>风险原因</div>
            <ul style={panelStyles.reasonList}>
              {unit.risk_reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <ReadableBlock title="变更内容" entries={readableDiffEntries(unit)} />
        <ReadableBlock title="来源依据" entries={readableProvenanceEntries(unit)} />
      </section>
      {writeback ? <WritebackStatus writeback={writeback} /> : null}
    </>
  );
}

function MetadataItem({ label, value }: { label: string; value: string }) {
  return (
    <div style={panelStyles.metadataItem}>
      <div style={panelStyles.metadataLabel}>{label}</div>
      <div style={panelStyles.metadataValue}>{value}</div>
    </div>
  );
}

function ReadableBlock({
  title,
  entries,
}: {
  title: string;
  entries: Array<{ label: string; value: string }>;
}) {
  if (entries.length === 0) {
    return null;
  }
  return (
    <div style={panelStyles.readableBlock}>
      <div style={panelStyles.blockTitle}>{title}</div>
      <dl style={panelStyles.readableList}>
        {entries.map((entry) => (
          <div key={`${entry.label}:${entry.value}`} style={panelStyles.readableRow}>
            <dt style={panelStyles.readableLabel}>{entry.label}</dt>
            <dd style={panelStyles.readableValue}>{entry.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function shortDiffSummary(unit: RunViewChangeUnit): string {
  const diff = unit.diff;
  const summary =
    stringValue(diff.summary) ??
    stringValue(diff.preview) ??
    stringValue(diff.title) ??
    stringValue(diff.path);
  if (summary) {
    return summary;
  }
  return "这项变更包含结构化内容，请在右侧详情查看。";
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function readableText(value: unknown, maxLength = 220): string | null {
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  const text = stringValue(value);
  if (!text) return null;
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

function changeTargetEyebrow(unit: RunViewChangeUnit): string {
  return [roomLabel(unit.target.room), objectTypeLabel(unit.target.object_type)]
    .filter(Boolean)
    .join(" / ");
}

function changeTargetDescription(unit: RunViewChangeUnit): string {
  return (
    readableText(unit.target.path) ??
    readableText(unit.target.section_id) ??
    readableText(unit.target.object_id) ??
    `${roomLabel(unit.target.room)}中的一个条目`
  );
}

function reviewActionDescription(unit: RunViewChangeUnit): string {
  const labels: Record<string, string> = {
    create: "新增内容",
    update: "更新内容",
    upsert: "写入或更新",
    merge: "合并内容",
    delete: "删除内容",
    import: "导入资料",
    set: "设置调整",
    write_document_draft: "写入文档草稿",
    insert_claim: "写入论断",
    update_workspace_settings: "调整工作区设置",
    accept_sandbox_artifact: "保存沙盒产物",
  };
  return labels[unit.action] ?? unit.action.replaceAll("_", " ");
}

function commitRouteDescription(unit: RunViewChangeUnit): string {
  if (unit.default_apply_state === "draft_applied") {
    return "已作为草稿应用";
  }
  if (unit.outputId) {
    return "随已确认结果保存";
  }
  if (unit.materialization) {
    return "确认后直接写入工作区";
  }
  return "仅作为复核记录";
}

function readableDiffEntries(unit: RunViewChangeUnit): Array<{ label: string; value: string }> {
  const diff = unit.diff;
  return compactReadableEntries([
    ["标题", diff.title],
    ["摘要", diff.summary],
    ["预览", diff.preview],
    ["文件", diff.path ?? diff.name],
    ["目标段落", diff.section],
    ["变更说明", diff.reason ?? diff.description],
  ]);
}

function readableProvenanceEntries(unit: RunViewChangeUnit): Array<{ label: string; value: string }> {
  return compactReadableEntries([
    ["来源", unit.provenance.source ?? unit.provenance.kind],
    ["复核来源", unit.provenance.source_review_item_id],
    ["生成步骤", unit.provenance.node_id ?? unit.provenance.phase],
    ["对应结果", unit.outputId ? "有对应结果" : null],
    ["物化操作", unit.materialization ? materializationLabel(unit.materialization.operation) : null],
  ]);
}

function compactReadableEntries(
  entries: Array<[string, unknown]>,
): Array<{ label: string; value: string }> {
  const result: Array<{ label: string; value: string }> = [];
  for (const [label, rawValue] of entries) {
    const value = readableText(rawValue);
    if (value) {
      result.push({ label, value });
    }
  }
  return result;
}

function materializationLabel(operation: string): string {
  const labels: Record<string, string> = {
    "library.import_source": "导入资料库",
    "documents.upsert_prism_file": "更新文档",
    "memory.merge_items": "合并记忆",
    "decisions.set": "记录决策",
    "tasks.create": "创建任务",
    "sandbox.materialize_artifact": "保存沙盒产物",
    "settings.update": "更新设置",
  };
  return labels[operation] ?? operation;
}

function roomLabel(room: string): string {
  const labels: Record<string, string> = {
    documents: "文档",
    library: "资料库",
    memory: "记忆",
    decisions: "决策",
    tasks: "任务",
    sandbox: "沙盒",
    settings: "设置",
    review: "复核",
  };
  return labels[room] ?? room;
}

function objectTypeLabel(value: string): string {
  const labels: Record<string, string> = {
    document: "文档",
    claim: "论断",
    prism_file: "文档文件",
    source: "资料来源",
    memory_item: "记忆条目",
    decision: "决策",
    workspace_task: "任务",
    sandbox_artifact: "沙盒产物",
    workspace_settings: "工作区设置",
    review_note: "复核备注",
  };
  return labels[value] ?? value.replaceAll("_", " ");
}

function isBulkSelectableChangeUnit(unit: RunViewChangeUnit): boolean {
  return (
    unit.group === "needs_confirmation" &&
    isChangeUnitReviewActionable(unit) &&
    unit.risk !== "high" &&
    unit.risk !== "critical"
  );
}

function isUndoableReviewDecision(unit: RunViewChangeUnit): boolean {
  return (
    isChangeUnitReviewActionable(unit) &&
    (unit.state === "accepted" || unit.state === "rejected")
  );
}

function reviewActionStatusMessage(
  actionState: ChangeSetReviewActionState | undefined,
  executionId: string,
): string | null {
  if (!actionState || actionState.executionId !== executionId) {
    return null;
  }
  if (actionState.error) {
    return `复核失败：${actionState.error}`;
  }
  if (!actionState.action) {
    return null;
  }
  const actionLabel: Record<ChangeSetReviewAction, string> = {
    accept: "确认",
    reject: "拒绝",
    undo: "撤销",
  };
  return `正在${actionLabel[actionState.action]} ${actionState.unitIds.length} 项变更`;
}

function groupCountStyle(group: ChangeSetGroup): CSSProperties {
  const border =
    group === "blocked"
      ? "var(--wjn-risk-high-line)"
      : group === "accepted"
        ? "var(--wjn-risk-low-line)"
        : "var(--wjn-change-neutral-line)";
  const color =
    group === "blocked"
      ? "var(--wjn-risk-high)"
      : group === "accepted"
        ? "var(--wjn-risk-low)"
        : "var(--wjn-text-secondary)";
  return {
    ...styles.previewGroupCount,
    borderColor: border,
    color,
    background: "var(--wjn-surface)",
  };
}

function riskBadgeStyle(risk: ChangeRisk): CSSProperties {
  const tone: Record<ChangeRisk, CSSProperties> = {
    low: {
      color: "var(--wjn-risk-low)",
      backgroundColor: "var(--wjn-risk-low-soft)",
      border: "1px solid var(--wjn-risk-low-line)",
    },
    medium: {
      color: "var(--wjn-risk-medium)",
      backgroundColor: "var(--wjn-risk-medium-soft)",
      border: "1px solid var(--wjn-risk-medium-line)",
    },
    high: {
      color: "var(--wjn-risk-high)",
      backgroundColor: "var(--wjn-risk-high-soft)",
      border: "1px solid var(--wjn-risk-high-line)",
    },
    critical: {
      color: "var(--wjn-risk-critical)",
      backgroundColor: "var(--wjn-risk-critical-soft)",
      border: "1px solid var(--wjn-risk-critical-line)",
    },
  };
  return { ...panelStyles.badge, ...tone[risk] };
}

function stateBadgeStyle(state: RunViewChangeUnit["state"]): CSSProperties {
  const accepted = state === "accepted" || state === "draft_applied";
  const rejected = state === "rejected" || state === "undone";
  return {
    ...panelStyles.badge,
    color: accepted
      ? "var(--wjn-risk-low)"
      : rejected
        ? "var(--wjn-text-muted)"
        : state === "blocked"
          ? "var(--wjn-risk-high)"
          : "var(--wjn-blue)",
    backgroundColor: accepted
      ? "var(--wjn-risk-low-soft)"
      : rejected
        ? "var(--wjn-change-neutral-soft)"
        : state === "blocked"
          ? "var(--wjn-risk-high-soft)"
          : "var(--wjn-accent-soft)",
    border: accepted
      ? "1px solid var(--wjn-risk-low-line)"
      : rejected
        ? "1px solid var(--wjn-change-neutral-line)"
        : state === "blocked"
          ? "1px solid var(--wjn-risk-high-line)"
          : "1px solid var(--wjn-accent-line)",
  };
}

const visuallyHiddenStyle: CSSProperties = {
  position: "absolute",
  width: 1,
  height: 1,
  margin: -1,
  padding: 0,
  overflow: "hidden",
  clip: "rect(0 0 0 0)",
  whiteSpace: "nowrap",
  border: 0,
};

const panelStyles: Record<string, CSSProperties> = {
  summaryGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
    gap: 8,
    marginTop: 12,
  },
  summaryCell: {
    minWidth: 0,
    padding: "8px 9px",
    borderRadius: 8,
    border: "1px solid rgba(20,20,30,0.08)",
    background: "var(--wjn-surface-subtle)",
  },
  summaryValue: {
    fontSize: 16,
    lineHeight: 1.1,
    fontWeight: 800,
    fontVariantNumeric: "tabular-nums",
  },
  summaryLabel: {
    marginTop: 3,
    color: "var(--wjn-text-muted)",
    fontSize: 10.5,
    fontWeight: 700,
  },
  toolbar: {
    display: "flex",
    alignItems: "center",
    gap: 7,
    marginTop: 12,
    flexWrap: "wrap",
  },
  actionBar: {
    display: "flex",
    alignItems: "center",
    gap: 7,
    marginTop: 8,
    flexWrap: "wrap",
  },
  selectionCount: {
    color: "var(--wjn-text-muted)",
    fontSize: 12,
    fontVariantNumeric: "tabular-nums",
  },
  groupStack: {
    display: "grid",
    gap: 12,
    marginTop: 14,
  },
  group: {
    display: "grid",
    gap: 8,
  },
  groupDetail: {
    color: "var(--wjn-text-muted)",
    fontSize: 11.5,
    lineHeight: 1.35,
  },
  unitList: {
    display: "grid",
    gap: 8,
  },
  unitRow: {
    display: "grid",
    gridTemplateColumns: "auto minmax(0, 1fr) auto",
    gap: 8,
    alignItems: "start",
    minWidth: 0,
    padding: 10,
    borderRadius: 8,
    border: "1px solid rgba(20,20,30,0.08)",
    background: "var(--wjn-surface)",
  },
  unitRowActive: {
    border: "1px solid var(--wjn-accent-line)",
    background: "var(--wjn-accent-soft)",
  },
  checkbox: {
    width: 16,
    height: 16,
    marginTop: 2,
    accentColor: "var(--wjn-blue)",
  },
  unitMainButton: {
    display: "grid",
    gap: 4,
    minWidth: 0,
    border: "none",
    padding: 0,
    background: "transparent",
    color: "inherit",
    textAlign: "left",
    cursor: "pointer",
  },
  unitTitleLine: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    minWidth: 0,
  },
  unitTitle: {
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    color: "var(--wjn-text)",
    fontSize: 12.5,
    fontWeight: 780,
  },
  unitSubtitle: {
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    color: "var(--wjn-text-muted)",
    fontSize: 11.5,
    lineHeight: 1.35,
  },
  badgeLine: {
    display: "flex",
    flexWrap: "wrap",
    gap: 5,
  },
  badge: {
    display: "inline-flex",
    alignItems: "center",
    minHeight: 20,
    padding: "2px 7px",
    borderRadius: 8,
    fontSize: 10.5,
    fontWeight: 760,
    whiteSpace: "nowrap",
  },
  expandButton: {
    width: 28,
    height: 28,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 8,
    border: "1px solid rgba(20,20,30,0.08)",
    background: "var(--wjn-surface)",
    color: "var(--wjn-text-secondary)",
    cursor: "pointer",
  },
  inlineDiff: {
    gridColumn: "2 / 4",
    display: "grid",
    gap: 5,
    minWidth: 0,
    paddingTop: 7,
    borderTop: "1px solid rgba(20,20,30,0.07)",
  },
  inlineDiffHeader: {
    display: "inline-flex",
    alignItems: "center",
    gap: 5,
    color: "var(--wjn-text-secondary)",
    fontSize: 11.5,
    fontWeight: 750,
  },
  inlineDiffText: {
    color: "var(--wjn-text-muted)",
    fontSize: 11.5,
    lineHeight: 1.45,
    whiteSpace: "pre-wrap",
    overflowWrap: "anywhere",
  },
  detailPanel: {
    display: "grid",
    gap: 13,
    padding: 13,
    borderRadius: 8,
    border: "1px solid rgba(20,20,30,0.08)",
    background: "var(--wjn-surface)",
  },
  detailHeader: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "flex-start",
    minWidth: 0,
  },
  detailEyebrow: {
    color: "var(--wjn-text-muted)",
    fontSize: 10.5,
    fontWeight: 780,
    textTransform: "uppercase",
  },
  detailTitle: {
    margin: "3px 0 0",
    color: "var(--wjn-text)",
    fontSize: 16,
    lineHeight: 1.25,
    fontWeight: 820,
  },
  detailSubtitle: {
    marginTop: 5,
    color: "var(--wjn-text-muted)",
    fontSize: 12,
    lineHeight: 1.45,
  },
  detailActions: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  readOnlyNotice: {
    padding: "8px 10px",
    borderRadius: 8,
    border: "1px solid rgba(20,20,30,0.08)",
    background: "rgba(245,247,250,0.9)",
    color: "var(--wjn-text-secondary)",
    fontSize: 12,
    lineHeight: 1.45,
  },
  metadataGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 8,
  },
  metadataItem: {
    minWidth: 0,
    padding: "8px 9px",
    borderRadius: 8,
    border: "1px solid rgba(20,20,30,0.08)",
    background: "var(--wjn-surface-subtle)",
  },
  metadataLabel: {
    color: "var(--wjn-text-muted)",
    fontSize: 10.5,
    fontWeight: 750,
  },
  metadataValue: {
    marginTop: 3,
    color: "var(--wjn-text-secondary)",
    fontSize: 12,
    lineHeight: 1.4,
    overflowWrap: "anywhere",
  },
  reasonBlock: {
    display: "grid",
    gap: 6,
  },
  reasonList: {
    margin: 0,
    paddingLeft: 18,
    color: "var(--wjn-text-secondary)",
    fontSize: 12,
    lineHeight: 1.5,
  },
  readableBlock: {
    display: "grid",
    gap: 6,
  },
  blockTitle: {
    color: "var(--wjn-text)",
    fontSize: 12,
    fontWeight: 780,
  },
  readableList: {
    margin: 0,
    display: "grid",
    gap: 6,
  },
  readableRow: {
    display: "grid",
    gridTemplateColumns: "84px minmax(0, 1fr)",
    gap: 8,
    padding: "8px 9px",
    borderRadius: 8,
    border: "1px solid rgba(20,20,30,0.08)",
    background: "rgba(245,247,250,0.88)",
  },
  readableLabel: {
    color: "var(--wjn-text-muted)",
    fontSize: 11,
    fontWeight: 760,
  },
  readableValue: {
    margin: 0,
    color: "var(--wjn-text-secondary)",
    fontSize: 12,
    lineHeight: 1.45,
    overflowWrap: "anywhere",
  },
};
