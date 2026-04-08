import {
  executeWorkspaceFeature,
  type ExecuteWorkspaceFeatureResponse,
  type WorkspaceFeature,
} from "@/lib/api";

function readNumberDetail(
  detail: Record<string, unknown> | null | undefined,
  key: string
): number | null {
  const value = detail?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function getWorkspaceFeatureExecutionWarningMessage(
  execution: Pick<
    ExecuteWorkspaceFeatureResponse,
    "warning" | "detail" | "message"
  >,
  fallback: string
): string {
  if (execution.warning === "literature_insufficient") {
    const current = readNumberDetail(execution.detail ?? null, "current");
    const recommended = readNumberDetail(execution.detail ?? null, "recommended");
    if (current !== null || recommended !== null) {
      return `文献数量不足（当前 ${current ?? 0} / 推荐 ${recommended ?? 0}），请先在「文献管理」中补充文献。`;
    }
  }

  return execution.message || fallback;
}

export function ensureWorkspaceFeatureTaskCreated(
  execution: ExecuteWorkspaceFeatureResponse,
  fallbacks: {
    warningFallback: string;
    missingTaskFallback: string;
  }
): {
  taskId: string;
  message: string;
  execution: ExecuteWorkspaceFeatureResponse;
} {
  if (execution.status === "warning" && !execution.task_id) {
    throw new Error(
      getWorkspaceFeatureExecutionWarningMessage(
        execution,
        fallbacks.warningFallback
      )
    );
  }

  if (!execution.task_id) {
    throw new Error(fallbacks.missingTaskFallback);
  }

  return {
    taskId: execution.task_id,
    message: execution.message,
    execution,
  };
}

export async function createWorkspaceFeatureTask(options: {
  workspaceId: string;
  featureId: string;
  params: Record<string, unknown>;
  threadId?: string;
  warningFallback: string;
  missingTaskFallback: string;
}): Promise<{
  taskId: string;
  message: string;
  execution: ExecuteWorkspaceFeatureResponse;
}> {
  const execution = await executeWorkspaceFeature(
    options.workspaceId,
    options.featureId,
    options.params,
    options.threadId
  );

  return ensureWorkspaceFeatureTaskCreated(execution, {
    warningFallback: options.warningFallback,
    missingTaskFallback: options.missingTaskFallback,
  });
}

type StartTaskFn = (params: {
  workspaceId?: string | null;
  taskId?: string;
  featureId: string;
  agent: string;
  agentLabel: string;
  stages: WorkspaceFeature["stages"];
  initialThinking?: string;
}) => string;

export function trackWorkspaceFeatureTask(options: {
  workspaceId?: string | null;
  feature: Pick<WorkspaceFeature, "id" | "agent" | "agentLabel" | "stages">;
  startTask: StartTaskFn;
  taskId: string;
  initialThinking?: string;
}): void {
  const { workspaceId, feature, startTask, taskId, initialThinking } = options;
  startTask({
    workspaceId,
    taskId,
    featureId: feature.id,
    agent: feature.agent,
    agentLabel: feature.agentLabel,
    stages: feature.stages,
    initialThinking,
  });
}
