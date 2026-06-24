import { authorizedFetch, readErrorMessage } from "@/lib/api/client";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";

export interface CommitRoomTarget {
  output_id: string;
  item_id: string;
}

export type CommitRoomName =
  | "documents"
  | "library"
  | "memory"
  | "decisions"
  | "tasks";

const COMMIT_ROOM_NAMES = [
  "documents",
  "library",
  "memory",
  "decisions",
  "tasks",
] as const satisfies readonly CommitRoomName[];

const COMMIT_ROOM_NAME_SET = new Set<string>(COMMIT_ROOM_NAMES);

export type CommitRoomTargets = Partial<Record<CommitRoomName, CommitRoomTarget[]>>;

export interface ExecutionCommitState {
  status: "committed" | "discarded";
  accepted_ids: string[];
  rejected_ids: string[];
  counts: Record<string, number>;
  room_targets: CommitRoomTargets;
  committed_at: string;
  review_batch_id?: string;
}

export interface ExecutionCommitResponse {
  committed?: Record<string, number>;
  room_targets?: CommitRoomTargets;
  commit_state?: ExecutionCommitState;
}

export interface ExecutionCommitRequest {
  accept_all?: boolean;
  accepted_ids?: string[];
  output_overrides?: Record<
    string,
    { data?: Record<string, unknown>; preview?: string }
  >;
}

export interface CommittedRoomLink {
  key: string;
  label: string;
  href: string;
}

export const COMMIT_STATE_SYNC_ERROR = "保存状态同步失败，请刷新后重试";

export async function commitExecutionOutputs(options: {
  executionId: string;
  idempotencyKey: string;
  body: ExecutionCommitRequest;
}): Promise<ExecutionCommitResponse> {
  const response = await authorizedFetch(
    `/api/executions/${options.executionId}/commit`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": options.idempotencyKey,
      },
      body: JSON.stringify(options.body),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "保存结果失败"));
  }
  return (await response.json()) as ExecutionCommitResponse;
}

export function buildCommittedRoomLinks(options: {
  workspaceId?: string | null;
  previews: WorkspaceResultPreview[];
  roomTargets?: CommitRoomTargets | null;
}): CommittedRoomLink[] {
  const { workspaceId, previews, roomTargets } = options;
  if (!workspaceId || !roomTargets) {
    return [];
  }

  const previewById = new Map(previews.map((preview) => [preview.id, preview]));
  const links: CommittedRoomLink[] = [];

  for (const target of roomTargets.documents ?? []) {
    const preview = previewById.get(target.output_id);
    const query = preview?.roomTarget?.query ?? preview?.title ?? null;
    links.push({
      key: `documents:${target.item_id}`,
      label: `打开已保存的 ${preview?.title ?? target.item_id}`,
      href: buildWorkspaceRoomHref({
        workspaceId,
        room: "documents",
        itemId: target.item_id,
        query,
      }),
    });
  }

  for (const target of roomTargets.library ?? []) {
    const preview = previewById.get(target.output_id);
    const query = preview?.roomTarget?.query ?? preview?.title ?? null;
    links.push({
      key: `library:${target.item_id}`,
      label: `打开已保存的 ${preview?.title ?? target.item_id}`,
      href: buildWorkspaceRoomHref({
        workspaceId,
        room: "library",
        itemId: target.item_id,
        query,
      }),
    });
  }

  for (const target of roomTargets.memory ?? []) {
    const preview = previewById.get(target.output_id);
    links.push({
      key: `memory:${target.item_id}`,
      label: `打开已保存的 ${preview?.title ?? "记忆"}`,
      href: buildWorkspaceRoomHref({
        workspaceId,
        room: "memory",
        itemId: target.item_id,
        query: preview?.title ?? null,
      }),
    });
  }

  for (const target of roomTargets.decisions ?? []) {
    const preview = previewById.get(target.output_id);
    links.push({
      key: `decisions:${target.item_id}`,
      label: `打开已保存的 ${preview?.title ?? "决策"}`,
      href: buildWorkspaceRoomHref({
        workspaceId,
        room: "decisions",
        itemId: target.item_id,
        query: preview?.title ?? null,
      }),
    });
  }

  for (const target of roomTargets.tasks ?? []) {
    const preview = previewById.get(target.output_id);
    links.push({
      key: `tasks:${target.item_id}`,
      label: `打开已保存的 ${preview?.title ?? "任务"}`,
      href: buildWorkspaceRoomHref({
        workspaceId,
        room: "tasks",
        itemId: target.item_id,
        query: preview?.title ?? null,
      }),
    });
  }

  return links;
}

export function readCommitStateFromResult(
  result: unknown,
): ExecutionCommitState | null {
  const carrier = recordValue(result);
  if (!carrier) return null;
  const rawCommitState = carrier.commit_state;
  const state = recordValue(rawCommitState);
  if (!state) return null;
  const status =
    state.status === "committed" || state.status === "discarded"
      ? state.status
      : null;
  const acceptedIds = stringArrayValue(state.accepted_ids);
  const rejectedIds = stringArrayValue(state.rejected_ids);
  const committedAt = stringValue(state.committed_at);
  if (!status || !acceptedIds || !rejectedIds || !committedAt) {
    return null;
  }

  const counts = numberRecordValue(state.counts);
  const roomTargets = roomTargetsValue(state.room_targets);
  if (!counts || !roomTargets) {
    return null;
  }
  return {
    status,
    accepted_ids: acceptedIds,
    rejected_ids: rejectedIds,
    counts,
    room_targets: roomTargets,
    committed_at: committedAt,
    ...(stringValue(state.review_batch_id)
      ? { review_batch_id: stringValue(state.review_batch_id)! }
      : {}),
  };
}

export function isExecutionCommitted(
  commitState: ExecutionCommitState | null | undefined,
): boolean {
  return commitState?.status === "committed";
}

export function isExecutionDiscarded(
  commitState: ExecutionCommitState | null | undefined,
): boolean {
  return commitState?.status === "discarded";
}

export function commitStateRoomTargets(
  commitState: ExecutionCommitState | null | undefined,
): CommitRoomTargets | null {
  return commitState?.room_targets ?? null;
}

export function commitStateFromCommitResponse(
  response: ExecutionCommitResponse,
): ExecutionCommitState | null {
  return readCommitStateFromResult(response);
}

function buildWorkspaceRoomHref(options: {
  workspaceId: string;
  room: "documents" | "library" | "memory" | "decisions" | "tasks";
  itemId: string;
  query: string | null;
}): string {
  const params = new URLSearchParams();
  params.set("room", options.room);
  params.set("item_id", options.itemId);
  if (options.query) {
    params.set("query", options.query);
  }
  return `/workspaces/${options.workspaceId}?${params.toString()}`;
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function stringArrayValue(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  const strings = value.filter(
    (item): item is string => typeof item === "string" && item.trim().length > 0,
  );
  return strings.length === value.length ? strings : null;
}

function numberRecordValue(value: unknown): Record<string, number> | null {
  const raw = recordValue(value);
  if (!raw) return null;
  const counts: Record<string, number> = {};
  for (const [key, item] of Object.entries(raw)) {
    if (!COMMIT_ROOM_NAME_SET.has(key)) {
      return null;
    }
    if (typeof item !== "number" || !Number.isFinite(item) || item < 0) {
      return null;
    }
    counts[key] = item;
  }
  return counts;
}

function roomTargetsValue(value: unknown): CommitRoomTargets | null {
  const raw = recordValue(value);
  if (!raw) return null;
  const targets: CommitRoomTargets = {};
  for (const key of Object.keys(raw)) {
    if (!COMMIT_ROOM_NAME_SET.has(key)) {
      return null;
    }
  }
  for (const room of COMMIT_ROOM_NAMES) {
    const rawTargets = raw[room];
    if (!Array.isArray(rawTargets)) continue;
    const roomTargets: CommitRoomTarget[] = [];
    for (const item of rawTargets) {
      const target = recordValue(item);
      const outputId = stringValue(target?.output_id);
      const itemId = stringValue(target?.item_id);
      if (!outputId || !itemId) {
        return null;
      }
      roomTargets.push({ output_id: outputId, item_id: itemId });
    }
    if (roomTargets.length > 0) {
      targets[room] = roomTargets;
    }
  }
  return targets;
}
