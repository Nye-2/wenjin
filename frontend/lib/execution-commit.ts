import { authorizedFetch, readErrorMessage } from "@/lib/api/client";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";

export interface CommitRoomTarget {
  output_id: string;
  item_id: string;
}

export interface ExecutionCommitResponse {
  committed?: Record<string, number>;
  room_targets?: {
    documents?: CommitRoomTarget[];
    library?: CommitRoomTarget[];
    memory?: CommitRoomTarget[];
    decisions?: CommitRoomTarget[];
    tasks?: CommitRoomTarget[];
  };
}

export interface CommittedRoomLink {
  key: string;
  label: string;
  href: string;
}

export async function commitExecutionOutputs(options: {
  executionId: string;
  idempotencyKey: string;
  body: Record<string, unknown>;
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
    throw new Error(await readErrorMessage(response, "Failed to save outputs"));
  }
  return (await response.json()) as ExecutionCommitResponse;
}

export function buildCommittedRoomLinks(options: {
  workspaceId?: string | null;
  previews: WorkspaceResultPreview[];
  roomTargets?: ExecutionCommitResponse["room_targets"];
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
      label: `打开已保存的 ${preview?.title ?? "Memory"}`,
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
      label: `打开已保存的 ${preview?.title ?? "Decision"}`,
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
      label: `打开已保存的 ${preview?.title ?? "Task"}`,
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
