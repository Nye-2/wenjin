import { filterVisibleWorkspaceResultItems } from "./workspace-result-kind";
import type { WorkspaceResultPreview } from "./workspace-result-preview";

export type WriteMode = "auto_draft" | "ask_workspace_write" | "strict_review";
export type ChangeRisk = "low" | "medium" | "high" | "critical";
export type ChangeApplyState =
  | "draft_applied"
  | "staged"
  | "accepted"
  | "rejected"
  | "blocked"
  | "undone";

export interface ChangeTarget {
  room: string;
  object_type: string;
  object_id?: string | null;
  path?: string | null;
  section_id?: string | null;
}

export interface ChangeMaterialization {
  operation: string;
  payload: Record<string, unknown>;
}

export interface ChangeUnit {
  id: string;
  target: ChangeTarget;
  action: string;
  risk: ChangeRisk;
  risk_reasons: string[];
  default_apply_state: ChangeApplyState;
  requires_confirmation: boolean;
  diff: Record<string, unknown>;
  provenance: Record<string, unknown>;
  rollback: Record<string, unknown>;
  materialization?: ChangeMaterialization | null;
}

export interface ChangeSet {
  execution_id: string;
  workspace_id: string;
  write_mode: WriteMode;
  units: ChangeUnit[];
  summary: string;
  created_at: string;
}

export interface ChangeSetReviewState {
  schema_version: string;
  accepted_unit_ids: string[];
  rejected_unit_ids: string[];
  undone_unit_ids: string[];
  updated_at: string;
}

export interface ChangeSetUnitState {
  unit_id: string;
  default_apply_state: ChangeApplyState;
  state: ChangeApplyState;
}

export interface ExecutionChangeSetResponse {
  change_set: ChangeSet;
  review_state: ChangeSetReviewState;
  unit_states: ChangeSetUnitState[];
}

export type ChangeSetGroup =
  | "draft_applied"
  | "needs_confirmation"
  | "blocked"
  | "accepted"
  | "rejected"
  | "undone";

export interface RunViewChangeUnit extends ChangeUnit {
  state: ChangeApplyState;
  group: ChangeSetGroup;
  title: string;
  subtitle: string;
  stateLabel: string;
  riskLabel: string;
  outputId?: string | null;
}

export interface RunViewChangeSet {
  executionId: string;
  workspaceId: string;
  writeMode: WriteMode;
  summary: string;
  units: RunViewChangeUnit[];
  reviewState: ChangeSetReviewState;
  counts: Record<ChangeSetGroup, number>;
  pendingCount: number;
}

export interface RunViewChangeSetReceiptTarget {
  output_id?: string;
  item_id?: string;
  file_id?: string;
  path?: string;
  content_hash?: string;
  document_id?: string;
  revision?: string;
}

export interface RunViewChangeSetReceipt {
  schemaVersion: string;
  retention: "compacted_after_commit";
  executionId: string | null;
  workspaceId: string | null;
  writeMode: WriteMode | null;
  summary: string | null;
  unitCount: number;
  acceptedUnitIds: string[];
  rejectedUnitIds: string[];
  undoneUnitIds: string[];
  acceptedOutputIds: string[];
  rejectedOutputIds: string[];
  committedAt: string | null;
  targets: Record<string, RunViewChangeSetReceiptTarget[]>;
}

const CHANGE_RISKS = new Set(["low", "medium", "high", "critical"]);
const APPLY_STATES = new Set([
  "draft_applied",
  "staged",
  "accepted",
  "rejected",
  "blocked",
  "undone",
]);
const WRITE_MODES = new Set(["auto_draft", "ask_workspace_write", "strict_review"]);

export function changeSetViewFromResult(result: unknown): RunViewChangeSet | null {
  const carrier = recordValue(result);
  if (!carrier) return null;
  const changeSet = changeSetFromUnknown(carrier.change_set);
  if (!changeSet) return null;
  const reviewState = reviewStateFromUnknown(carrier.change_set_review_state);
  const stateByUnitId = new Map(
    unitStatesFromUnknown(carrier.unit_states).map((item) => [item.unit_id, item.state]),
  );
  const units = changeSet.units.map((unit) => {
    const state =
      stateByUnitId.get(unit.id) ??
      effectiveStateFromReviewState(unit.id, unit.default_apply_state, reviewState);
    const group = groupForState(state);
    return {
      ...unit,
      state,
      group,
      title: titleForUnit(unit),
      subtitle: subtitleForUnit(unit),
      stateLabel: stateLabel(state),
      riskLabel: riskLabel(unit.risk),
      outputId: stringValue(unit.provenance.output_id),
    };
  });
  const counts = countGroups(units);
  return {
    executionId: changeSet.execution_id,
    workspaceId: changeSet.workspace_id,
    writeMode: changeSet.write_mode,
    summary: changeSet.summary,
    units,
    reviewState,
    counts,
    pendingCount: counts.needs_confirmation + counts.blocked,
  };
}

export function changeSetViewFromResponse(
  response: ExecutionChangeSetResponse,
): RunViewChangeSet | null {
  return changeSetViewFromResult({
    change_set: response.change_set,
    change_set_review_state: response.review_state,
    unit_states: response.unit_states,
  });
}

export function changeSetReceiptFromResult(
  result: unknown,
): RunViewChangeSetReceipt | null {
  const carrier = recordValue(result);
  const raw = recordValue(carrier?.change_set_receipt);
  if (!raw) return null;
  const schemaVersion = stringValue(raw.schema_version);
  const retention = stringValue(raw.retention);
  if (
    schemaVersion !== "wenjin.change_set.receipt.v1" ||
    retention !== "compacted_after_commit"
  ) {
    return null;
  }
  return {
    schemaVersion,
    retention,
    executionId: stringValue(raw.execution_id),
    workspaceId: stringValue(raw.workspace_id),
    writeMode: writeModeValue(raw.write_mode),
    summary: stringValue(raw.summary),
    unitCount: numberValue(raw.unit_count) ?? 0,
    acceptedUnitIds: stringArrayValue(raw.accepted_unit_ids),
    rejectedUnitIds: stringArrayValue(raw.rejected_unit_ids),
    undoneUnitIds: stringArrayValue(raw.undone_unit_ids),
    acceptedOutputIds: stringArrayValue(raw.accepted_output_ids),
    rejectedOutputIds: stringArrayValue(raw.rejected_output_ids),
    committedAt: stringValue(raw.committed_at),
    targets: receiptTargetsFromUnknown(raw.targets),
  };
}

export function acceptedOutputIdsFromChangeSet(
  changeSet: RunViewChangeSet | null,
): string[] {
  if (!changeSet) return [];
  const unitsByOutputId = new Map<string, RunViewChangeUnit[]>();
  for (const unit of changeSet.units) {
    if (!unit.outputId) {
      continue;
    }
    const existing = unitsByOutputId.get(unit.outputId);
    if (existing) {
      existing.push(unit);
    } else {
      unitsByOutputId.set(unit.outputId, [unit]);
    }
  }
  const ids: string[] = [];
  for (const [outputId, units] of unitsByOutputId.entries()) {
    const allAccepted = units.every((unit) => unit.state === "accepted");
    const hasBlockedUnit = units.some(
      (unit) => unit.default_apply_state === "blocked",
    );
    if (allAccepted && !hasBlockedUnit) {
      ids.push(outputId);
    }
  }
  return ids;
}

export function acceptedUnitIdsFromChangeSet(
  changeSet: RunViewChangeSet | null,
): string[] {
  if (!changeSet) return [];
  const unitsByOutputId = new Map<string, RunViewChangeUnit[]>();
  const materializedUnitIds: string[] = [];
  for (const unit of changeSet.units) {
    if (!unit.outputId) {
      if (
        unit.materialization &&
        unit.state === "accepted" &&
        unit.default_apply_state !== "blocked"
      ) {
        materializedUnitIds.push(unit.id);
      }
      continue;
    }
    const existing = unitsByOutputId.get(unit.outputId);
    if (existing) {
      existing.push(unit);
    } else {
      unitsByOutputId.set(unit.outputId, [unit]);
    }
  }

  const ids: string[] = [];
  for (const units of unitsByOutputId.values()) {
    const allAccepted = units.every((unit) => unit.state === "accepted");
    const hasBlockedUnit = units.some(
      (unit) => unit.default_apply_state === "blocked",
    );
    if (allAccepted && !hasBlockedUnit) {
      ids.push(...units.map((unit) => unit.id));
    }
  }
  return [...ids, ...materializedUnitIds];
}

export function commitPreviewsForChangeSetReview({
  changeSet,
  previews,
  visiblePreviews,
}: {
  changeSet: RunViewChangeSet | null;
  previews: WorkspaceResultPreview[];
  visiblePreviews?: WorkspaceResultPreview[];
}): WorkspaceResultPreview[] {
  if (!changeSet) {
    const reviewablePreviews =
      visiblePreviews ?? filterVisibleWorkspaceResultItems(previews);
    return reviewablePreviews.filter(
      (preview) => preview.canCommit && preview.defaultChecked,
    );
  }

  const acceptedOutputIds = new Set(acceptedOutputIdsFromChangeSet(changeSet));
  return previews.filter(
    (preview) => preview.canCommit && acceptedOutputIds.has(preview.id),
  );
}

export function isChangeUnitPendingReview(
  unit: Pick<RunViewChangeUnit, "group">,
): boolean {
  return unit.group === "needs_confirmation" || unit.group === "blocked";
}

export function isChangeUnitReviewActionable(
  unit: Pick<RunViewChangeUnit, "group" | "state">,
): boolean {
  return unit.group !== "draft_applied" && unit.state !== "draft_applied";
}

export function responseResultPatch(
  response: ExecutionChangeSetResponse,
): Record<string, unknown> {
  return {
    change_set: response.change_set,
    change_set_review_state: response.review_state,
    unit_states: response.unit_states,
  };
}

function changeSetFromUnknown(value: unknown): ChangeSet | null {
  const raw = recordValue(value);
  if (!raw) return null;
  const executionId = stringValue(raw.execution_id);
  const workspaceId = stringValue(raw.workspace_id);
  const writeMode = writeModeValue(raw.write_mode);
  const summary = stringValue(raw.summary) ?? "";
  const createdAt = stringValue(raw.created_at) ?? "";
  const units = arrayValue(raw.units)
    .map(changeUnitFromUnknown)
    .filter((unit): unit is ChangeUnit => Boolean(unit));
  if (!executionId || !workspaceId || !writeMode || units.length === 0) {
    return null;
  }
  return {
    execution_id: executionId,
    workspace_id: workspaceId,
    write_mode: writeMode,
    units,
    summary,
    created_at: createdAt,
  };
}

function changeUnitFromUnknown(value: unknown): ChangeUnit | null {
  const raw = recordValue(value);
  if (!raw) return null;
  const id = stringValue(raw.id);
  const target = changeTargetFromUnknown(raw.target);
  const action = stringValue(raw.action);
  const risk = riskValue(raw.risk);
  const defaultState = applyStateValue(raw.default_apply_state);
  if (!id || !target || !action || !risk || !defaultState) {
    return null;
  }
  return {
    id,
    target,
    action,
    risk,
    risk_reasons: stringArrayValue(raw.risk_reasons),
    default_apply_state: defaultState,
    requires_confirmation: Boolean(raw.requires_confirmation),
    diff: recordValue(raw.diff) ?? {},
    provenance: recordValue(raw.provenance) ?? {},
    rollback: recordValue(raw.rollback) ?? {},
    materialization: changeMaterializationFromUnknown(raw.materialization),
  };
}

function changeMaterializationFromUnknown(
  value: unknown,
): ChangeMaterialization | null {
  const raw = recordValue(value);
  if (!raw) return null;
  const operation = stringValue(raw.operation);
  const payload = recordValue(raw.payload);
  if (!operation || !payload) return null;
  return { operation, payload };
}

function changeTargetFromUnknown(value: unknown): ChangeTarget | null {
  const raw = recordValue(value);
  if (!raw) return null;
  const room = stringValue(raw.room);
  const objectType = stringValue(raw.object_type);
  if (!room || !objectType) return null;
  return {
    room,
    object_type: objectType,
    object_id: stringValue(raw.object_id),
    path: stringValue(raw.path),
    section_id: stringValue(raw.section_id),
  };
}

function reviewStateFromUnknown(value: unknown): ChangeSetReviewState {
  const raw = recordValue(value) ?? {};
  return {
    schema_version:
      stringValue(raw.schema_version) ?? "wenjin.change_set.review_state.v1",
    accepted_unit_ids: stringArrayValue(raw.accepted_unit_ids),
    rejected_unit_ids: stringArrayValue(raw.rejected_unit_ids),
    undone_unit_ids: stringArrayValue(raw.undone_unit_ids),
    updated_at: stringValue(raw.updated_at) ?? "",
  };
}

function unitStatesFromUnknown(value: unknown): ChangeSetUnitState[] {
  return arrayValue(value)
    .map((item) => {
      const raw = recordValue(item);
      if (!raw) return null;
      const unitId = stringValue(raw.unit_id);
      const defaultState = applyStateValue(raw.default_apply_state);
      const state = applyStateValue(raw.state);
      if (!unitId || !defaultState || !state) return null;
      return { unit_id: unitId, default_apply_state: defaultState, state };
    })
    .filter((item): item is ChangeSetUnitState => Boolean(item));
}

function effectiveStateFromReviewState(
  unitId: string,
  defaultState: ChangeApplyState,
  reviewState: ChangeSetReviewState,
): ChangeApplyState {
  if (reviewState.undone_unit_ids.includes(unitId)) return "undone";
  if (reviewState.rejected_unit_ids.includes(unitId)) return "rejected";
  if (reviewState.accepted_unit_ids.includes(unitId)) return "accepted";
  return defaultState;
}

function groupForState(state: ChangeApplyState): ChangeSetGroup {
  if (state === "draft_applied") return "draft_applied";
  if (state === "blocked") return "blocked";
  if (state === "accepted") return "accepted";
  if (state === "rejected") return "rejected";
  if (state === "undone") return "undone";
  return "needs_confirmation";
}

function countGroups(units: RunViewChangeUnit[]): Record<ChangeSetGroup, number> {
  const counts: Record<ChangeSetGroup, number> = {
    draft_applied: 0,
    needs_confirmation: 0,
    blocked: 0,
    accepted: 0,
    rejected: 0,
    undone: 0,
  };
  for (const unit of units) {
    counts[unit.group] += 1;
  }
  return counts;
}

function titleForUnit(unit: ChangeUnit): string {
  const diff = unit.diff;
  return (
    stringValue(diff.title) ??
    stringValue(diff.name) ??
    stringValue(diff.summary) ??
    stringValue(unit.target.path) ??
    stringValue(unit.target.object_id) ??
    `${roomLabel(unit.target.room)}变更`
  );
}

function subtitleForUnit(unit: ChangeUnit): string {
  const path = stringValue(unit.target.path);
  const objectId = stringValue(unit.target.object_id);
  const target = [roomLabel(unit.target.room), objectTypeLabel(unit.target.object_type)]
    .filter(Boolean)
    .join(" / ");
  return [target, path ?? objectId, actionLabel(unit.action)]
    .filter(Boolean)
    .join(" · ");
}

function roomLabel(room: string): string {
  const labels: Record<string, string> = {
    documents: "文档",
    library: "资料库",
    memory: "记忆",
    decisions: "决策",
    tasks: "任务",
    sandbox: "沙盒",
    review: "复核",
  };
  return labels[room] ?? room;
}

function objectTypeLabel(value: string): string {
  const labels: Record<string, string> = {
    document: "文档",
    claim: "论断",
    prism_file: "文档文件",
    library_item: "资料条目",
    source: "资料来源",
    memory_item: "记忆条目",
    decision: "决策",
    workspace_task: "任务",
    artifact: "产物",
    sandbox_artifact: "沙盒产物",
    workspace_settings: "工作区设置",
    review_note: "复核备注",
  };
  return labels[value] ?? value.replaceAll("_", " ");
}

function actionLabel(value: string): string {
  const labels: Record<string, string> = {
    create: "新建",
    update: "更新",
    upsert: "写入",
    merge: "合并",
    delete: "删除",
    import: "导入",
    set: "设定",
    add_library_item: "加入资料库",
    write_document_draft: "写入文档草稿",
    insert_claim: "写入论断",
    update_workspace_settings: "调整工作区设置",
    accept_sandbox_artifact: "保存沙盒产物",
  };
  return labels[value] ?? value.replaceAll("_", " ");
}

function stateLabel(value: ChangeApplyState): string {
  const labels: Record<ChangeApplyState, string> = {
    draft_applied: "草稿已应用",
    staged: "待复核",
    accepted: "已确认",
    rejected: "已拒绝",
    blocked: "已阻断",
    undone: "已撤销",
  };
  return labels[value];
}

function riskLabel(value: ChangeRisk): string {
  const labels: Record<ChangeRisk, string> = {
    low: "低风险",
    medium: "中风险",
    high: "高风险",
    critical: "严重风险",
  };
  return labels[value];
}

function writeModeValue(value: unknown): WriteMode | null {
  return typeof value === "string" && WRITE_MODES.has(value)
    ? (value as WriteMode)
    : null;
}

function riskValue(value: unknown): ChangeRisk | null {
  return typeof value === "string" && CHANGE_RISKS.has(value)
    ? (value as ChangeRisk)
    : null;
}

function applyStateValue(value: unknown): ChangeApplyState | null {
  return typeof value === "string" && APPLY_STATES.has(value)
    ? (value as ChangeApplyState)
    : null;
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function stringArrayValue(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  const result: string[] = [];
  for (const item of value) {
    const text = stringValue(item);
    if (!text || seen.has(text)) continue;
    result.push(text);
    seen.add(text);
  }
  return result;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0
    ? value
    : null;
}

function receiptTargetsFromUnknown(
  value: unknown,
): Record<string, RunViewChangeSetReceiptTarget[]> {
  const raw = recordValue(value) ?? {};
  const targets: Record<string, RunViewChangeSetReceiptTarget[]> = {};
  for (const [room, items] of Object.entries(raw)) {
    if (!Array.isArray(items)) {
      targets[room] = [];
      continue;
    }
    targets[room] = items
      .map(receiptTargetFromUnknown)
      .filter((item): item is RunViewChangeSetReceiptTarget => item !== null);
  }
  return targets;
}

function receiptTargetFromUnknown(
  value: unknown,
): RunViewChangeSetReceiptTarget | null {
  const raw = recordValue(value);
  if (!raw) return null;
  const target: RunViewChangeSetReceiptTarget = {};
  for (const key of [
    "output_id",
    "item_id",
    "file_id",
    "path",
    "content_hash",
    "document_id",
    "revision",
  ] as const) {
    const text = stringValue(raw[key]);
    if (text) {
      target[key] = text;
    }
  }
  return Object.keys(target).length > 0 ? target : null;
}
