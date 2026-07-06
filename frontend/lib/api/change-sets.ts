import { authorizedFetch, readErrorMessage } from "@/lib/api/client";
import type { ExecutionChangeSetResponse } from "@/lib/change-set-view";

export async function getExecutionChangeSet(
  executionId: string,
): Promise<ExecutionChangeSetResponse> {
  const response = await authorizedFetch(
    `/api/executions/${executionId}/changeset`,
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "读取审阅变更失败"));
  }
  return (await response.json()) as ExecutionChangeSetResponse;
}

export async function acceptExecutionChangeSetUnits(options: {
  executionId: string;
  unitIds: string[];
}): Promise<ExecutionChangeSetResponse> {
  return mutateExecutionChangeSetUnits({
    executionId: options.executionId,
    unitIds: options.unitIds,
    action: "accept",
    fallback: "接受变更失败",
  });
}

export async function rejectExecutionChangeSetUnits(options: {
  executionId: string;
  unitIds: string[];
}): Promise<ExecutionChangeSetResponse> {
  return mutateExecutionChangeSetUnits({
    executionId: options.executionId,
    unitIds: options.unitIds,
    action: "reject",
    fallback: "拒绝变更失败",
  });
}

export async function undoExecutionChangeSetUnits(options: {
  executionId: string;
  unitIds: string[];
}): Promise<ExecutionChangeSetResponse> {
  return mutateExecutionChangeSetUnits({
    executionId: options.executionId,
    unitIds: options.unitIds,
    action: "undo",
    fallback: "撤销变更状态失败",
  });
}

async function mutateExecutionChangeSetUnits(options: {
  executionId: string;
  unitIds: string[];
  action: "accept" | "reject" | "undo";
  fallback: string;
}): Promise<ExecutionChangeSetResponse> {
  const response = await authorizedFetch(
    `/api/executions/${options.executionId}/changeset/${options.action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ unit_ids: options.unitIds }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, options.fallback));
  }
  return (await response.json()) as ExecutionChangeSetResponse;
}
