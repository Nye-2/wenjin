export type TaskRuntimePhaseStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export interface TaskRuntimePhase {
  id: string;
  label: string;
  description?: string;
  status: TaskRuntimePhaseStatus;
  progress?: number;
}

export interface TaskRuntimeMetricEntry {
  label: string;
  value: string;
}

export interface TaskRuntimeListItem {
  title: string;
  description?: string;
  meta?: string;
  badge?: string | null;
}

export interface TaskRuntimeActivityItem {
  title: string;
  description?: string;
  tone?: "info" | "success" | "warning" | "danger";
  timestamp?: string;
}

export type TaskRuntimeBlock =
  | {
      id: string;
      phase_id?: string;
      kind: "metrics";
      title: string;
      description?: string;
      entries: TaskRuntimeMetricEntry[];
    }
  | {
      id: string;
      phase_id?: string;
      kind: "list";
      title: string;
      description?: string;
      items: TaskRuntimeListItem[];
    }
  | {
      id: string;
      phase_id?: string;
      kind: "activity";
      title: string;
      description?: string;
      items: TaskRuntimeActivityItem[];
    }
  | {
      id: string;
      phase_id?: string;
      kind: "text";
      title: string;
      description?: string;
      content: string;
    };

export interface TaskRuntimeState {
  title?: string;
  current_phase?: string;
  phases?: TaskRuntimePhase[];
  blocks?: TaskRuntimeBlock[];
  updated_at?: string;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function extractTaskRuntime(
  metadata: Record<string, unknown> | null | undefined
): TaskRuntimeState | null {
  if (!metadata) {
    return null;
  }

  const runtime = metadata.runtime;
  if (!isObject(runtime)) {
    return null;
  }

  return runtime as unknown as TaskRuntimeState;
}
