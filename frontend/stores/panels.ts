import { create } from "zustand";
import { listTasks, type TaskStatus, type WorkspaceFeature, type WorkspaceSubagentUpdatedEvent, type WorkspaceTaskEvent } from "@/lib/api";
import { extractTaskRuntime, type TaskRuntimeState } from "@/lib/task-runtime";

export interface FeaturePanelSubagent {
  id: string;
  threadId: string;
  subagentType: string | null;
  status: string;
  outputPreview: string | null;
  error: string | null;
  updatedAt: string;
}

export interface FeaturePanelSession {
  taskId: string;
  workspaceId: string;
  threadId: string | null;
  featureId: string;
  title: string;
  description: string;
  panelKey: string | null;
  status: string;
  progress: number;
  message: string | null;
  currentStep: string | null;
  runtime: TaskRuntimeState | null;
  result: Record<string, unknown> | null;
  error: string | null;
  action: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  updatedAt: string;
  subagents: FeaturePanelSubagent[];
}

export type FeaturePanelWorkspaceState = WorkspacePanelState;
export interface GroupedFeaturePanelSessions {
  active: FeaturePanelSession[];
  recent: FeaturePanelSession[];
  completed: FeaturePanelSession[];
}

interface WorkspacePanelState {
  activeSessionId: string | null;
  sessions: FeaturePanelSession[];
}

interface FeaturePanelStoreState {
  byWorkspace: Record<string, WorkspacePanelState>;
  hydrateWorkspace: (
    workspaceId: string,
    featureResolver: (featureId: string) => WorkspaceFeature | undefined,
  ) => Promise<void>;
  upsertTaskSession: (
    workspaceId: string,
    task: WorkspaceTaskEvent["task"] | TaskStatus,
    featureResolver: (featureId: string) => WorkspaceFeature | undefined,
  ) => void;
  appendSubagentUpdate: (
    workspaceId: string,
    event: WorkspaceSubagentUpdatedEvent,
  ) => void;
  setActiveSession: (workspaceId: string, taskId: string | null) => void;
  dismissSession: (workspaceId: string, taskId: string) => void;
  clearWorkspace: (workspaceId: string) => void;
}

function createWorkspacePanelState(): WorkspacePanelState {
  return {
    activeSessionId: null,
    sessions: [],
  };
}

function coerceTaskResult(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function selectPreferredSessionId(sessions: FeaturePanelSession[]): string | null {
  const running = sessions
    .filter((session) => session.status === "running" || session.status === "pending")
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
  if (running.length > 0) {
    return running[0].taskId;
  }

  const latest = [...sessions].sort((left, right) =>
    right.updatedAt.localeCompare(left.updatedAt)
  );
  return latest[0]?.taskId ?? null;
}

function buildSessionTitle(
  featureId: string,
  feature: WorkspaceFeature | undefined,
): string {
  if (feature?.name) {
    return feature.name;
  }
  return featureId.replace(/[_-]/g, " ").trim() || "工作面板";
}

function buildSessionDescription(
  feature: WorkspaceFeature | undefined,
  task: WorkspaceTaskEvent["task"] | TaskStatus,
): string {
  const message =
    typeof task.message === "string" && task.message.trim()
      ? task.message.trim()
      : null;
  if (message) {
    return message;
  }
  return feature?.description ?? "查看当前任务的工作流、中间结果与产出。";
}

function buildSessionFromTask(
  workspaceId: string,
  task: WorkspaceTaskEvent["task"] | TaskStatus,
  featureResolver: (featureId: string) => WorkspaceFeature | undefined,
  previous: FeaturePanelSession | null,
): FeaturePanelSession | null {
  const featureId =
    typeof task.feature_id === "string" && task.feature_id.trim()
      ? task.feature_id
      : null;
  const taskId =
    typeof task.task_id === "string" && task.task_id.trim()
      ? task.task_id
      : null;

  if (!featureId || !taskId) {
    return null;
  }

  const feature = featureResolver(featureId);
  const runtime = extractTaskRuntime(
    task.metadata && typeof task.metadata === "object"
      ? (task.metadata as Record<string, unknown>)
      : null
  );
  const result = coerceTaskResult(task.result);
  const createdAt =
    "created_at" in task && typeof task.created_at === "string"
      ? task.created_at
      : previous?.createdAt ?? new Date().toISOString();
  const startedAt =
    "started_at" in task && typeof task.started_at === "string"
      ? task.started_at
      : previous?.startedAt ?? null;
  const completedAt =
    "completed_at" in task && typeof task.completed_at === "string"
      ? task.completed_at
      : previous?.completedAt ?? null;
  const currentStep =
    "current_step" in task && typeof task.current_step === "string" && task.current_step.trim()
      ? task.current_step
      : previous?.currentStep ?? null;
  const action =
    "action" in task && typeof task.action === "string" && task.action.trim()
      ? task.action
      : previous?.action ?? null;
  const updatedAt =
    completedAt ??
    startedAt ??
    (task.metadata &&
    typeof task.metadata === "object" &&
    typeof (task.metadata as Record<string, unknown>).updated_at === "string"
      ? String((task.metadata as Record<string, unknown>).updated_at)
      : null) ??
    new Date().toISOString();

  return {
    taskId,
    workspaceId,
    threadId:
      typeof task.thread_id === "string" && task.thread_id.trim()
        ? task.thread_id
        : previous?.threadId ?? null,
    featureId,
    title: buildSessionTitle(featureId, feature),
    description: buildSessionDescription(feature, task),
    panelKey: feature?.panel ?? null,
    status: task.status,
    progress: typeof task.progress === "number" ? task.progress : previous?.progress ?? 0,
    message:
      typeof task.message === "string" && task.message.trim()
        ? task.message
        : previous?.message ?? null,
    currentStep,
    runtime: runtime ?? previous?.runtime ?? null,
    result: result ?? previous?.result ?? null,
    error:
      typeof task.error === "string" && task.error.trim()
        ? task.error
        : previous?.error ?? null,
    action:
      action,
    createdAt,
    startedAt,
    completedAt,
    updatedAt,
    subagents: previous?.subagents ?? [],
  };
}

function upsertSession(
  sessions: FeaturePanelSession[],
  nextSession: FeaturePanelSession,
): FeaturePanelSession[] {
  const filtered = sessions.filter((session) => session.taskId !== nextSession.taskId);
  const nextSessions = [nextSession, ...filtered];
  nextSessions.sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
  return nextSessions.slice(0, 12);
}

function selectSubagentTarget(
  workspace: WorkspacePanelState,
  event: WorkspaceSubagentUpdatedEvent,
): FeaturePanelSession | null {
  const runningForThread = workspace.sessions.find(
    (session) =>
      session.threadId === event.subagent.thread_id &&
      (session.status === "running" || session.status === "pending")
  );
  if (runningForThread) {
    return runningForThread;
  }

  const active = workspace.activeSessionId
    ? workspace.sessions.find((session) => session.taskId === workspace.activeSessionId) ?? null
    : null;
  if (active?.threadId === event.subagent.thread_id) {
    return active;
  }

  return active;
}

export const useFeaturePanelStore = create<FeaturePanelStoreState>((set) => ({
  byWorkspace: {},

  hydrateWorkspace: async (workspaceId, featureResolver) => {
    try {
      const response = await listTasks({
        workspace_id: workspaceId,
        limit: 12,
      });

      const sessions = response.tasks
        .map((task) => buildSessionFromTask(workspaceId, task, featureResolver, null))
        .filter((session): session is FeaturePanelSession => session !== null);

      set((state) => ({
        byWorkspace: {
          ...state.byWorkspace,
          [workspaceId]: {
            activeSessionId: selectPreferredSessionId(sessions),
            sessions,
          },
        },
      }));
    } catch {
      set((state) => ({
        byWorkspace: {
          ...state.byWorkspace,
          [workspaceId]: state.byWorkspace[workspaceId] ?? createWorkspacePanelState(),
        },
      }));
    }
  },

  upsertTaskSession: (workspaceId, task, featureResolver) => {
    set((state) => {
      const workspace = state.byWorkspace[workspaceId] ?? createWorkspacePanelState();
      const previous =
        typeof task.task_id === "string"
          ? workspace.sessions.find((session) => session.taskId === task.task_id) ?? null
          : null;
      const session = buildSessionFromTask(workspaceId, task, featureResolver, previous);
      if (!session) {
        return state;
      }

      const sessions = upsertSession(workspace.sessions, session);
      const activeSessionId =
        workspace.activeSessionId &&
        sessions.some((candidate) => candidate.taskId === workspace.activeSessionId)
          ? session.status === "running" || session.status === "pending"
            ? session.taskId
            : workspace.activeSessionId
          : selectPreferredSessionId(sessions);

      return {
        byWorkspace: {
          ...state.byWorkspace,
          [workspaceId]: {
            activeSessionId,
            sessions,
          },
        },
      };
    });
  },

  appendSubagentUpdate: (workspaceId, event) => {
    set((state) => {
      const workspace = state.byWorkspace[workspaceId];
      if (!workspace) {
        return state;
      }

      const target = selectSubagentTarget(workspace, event);
      if (!target) {
        return state;
      }

      const nextSubagent: FeaturePanelSubagent = {
        id: event.subagent.task_id,
        threadId: event.subagent.thread_id,
        subagentType:
          typeof event.subagent.subagent_type === "string"
            ? event.subagent.subagent_type
            : null,
        status: event.subagent.status,
        outputPreview:
          typeof event.subagent.output_preview === "string"
            ? event.subagent.output_preview
            : null,
        error:
          typeof event.subagent.error === "string"
            ? event.subagent.error
            : null,
        updatedAt: event.timestamp ?? new Date().toISOString(),
      };

      const sessions = workspace.sessions.map((session) => {
        if (session.taskId !== target.taskId) {
          return session;
        }

        const subagents = [
          nextSubagent,
          ...session.subagents.filter((item) => item.id !== nextSubagent.id),
        ].slice(0, 16);

        return {
          ...session,
          subagents,
          updatedAt: nextSubagent.updatedAt,
        };
      });

      return {
        byWorkspace: {
          ...state.byWorkspace,
          [workspaceId]: {
            ...workspace,
            sessions,
          },
        },
      };
    });
  },

  setActiveSession: (workspaceId, taskId) => {
    set((state) => ({
      byWorkspace: {
        ...state.byWorkspace,
        [workspaceId]: {
          ...(state.byWorkspace[workspaceId] ?? createWorkspacePanelState()),
          activeSessionId: taskId,
        },
      },
    }));
  },

  dismissSession: (workspaceId, taskId) => {
    set((state) => {
      const workspace = state.byWorkspace[workspaceId];
      if (!workspace) {
        return state;
      }

      const sessions = workspace.sessions.filter((session) => session.taskId !== taskId);
      return {
        byWorkspace: {
          ...state.byWorkspace,
          [workspaceId]: {
            activeSessionId:
              workspace.activeSessionId === taskId
                ? selectPreferredSessionId(sessions)
                : workspace.activeSessionId,
            sessions,
          },
        },
      };
    });
  },

  clearWorkspace: (workspaceId) => {
    set((state) => {
      const next = { ...state.byWorkspace };
      delete next[workspaceId];
      return { byWorkspace: next };
    });
  },
}));

export function groupFeaturePanelSessions(
  sessions: FeaturePanelSession[]
): GroupedFeaturePanelSessions {
  const active = sessions.filter(
    (session) => session.status === "running" || session.status === "pending"
  );
  const completed = sessions.filter(
    (session) => session.status === "success" || session.status === "failed"
  );
  const completedSorted = [...completed].sort((left, right) =>
    right.updatedAt.localeCompare(left.updatedAt)
  );

  return {
    active,
    recent: completedSorted.slice(0, 3),
    completed: completedSorted.slice(3),
  };
}
