/**
 * Reducer helpers for the workflow store.
 *
 * Pure functions that translate `subagent.updated` SSE events into the
 * `Run -> Phase -> Subagent` tree the LiveWorkflowPanel renders. Kept
 * separate from the zustand store so they can be tested without React.
 */

import type {
  WorkspaceSubagentUpdatedEvent,
  WorkspaceTaskEvent,
} from "@/lib/api/types";

export type SubagentStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "waiting"
  | "cancelled"
  | "timed_out";

export interface SubagentSnap {
  task_id: string;
  status: SubagentStatus | string;
  subagent_type?: string | null;
  output_preview?: string | null;
  output?: string | null;
  error?: string | null;
  token_usage?: { total?: number } | null;
  model_name?: string | null;
  duration_ms?: number;
}

export interface PhaseSnap {
  index: number;
  name: string;
  subagents: SubagentSnap[];
}

export type RunStatus =
  | "running"
  | "paused"
  | "completed"
  | "cancelled"
  | "failed";

export interface Run {
  id: string;
  thread_id: string;
  title: string;
  phases: PhaseSnap[];
  status: RunStatus;
  started_at: string;
}

export function asNumber(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v !== "") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

export function reduceTaskEvent(
  runs: Run[],
  task: WorkspaceTaskEvent["task"],
): Run[] {
  const runId = task.execution_session_id || task.task_id;
  const phaseIdx = -1;
  const phaseName = task.task_type || "task";

  const next = runs.slice();
  let runIdx = next.findIndex((r) => r.id === runId);
  if (runIdx === -1) {
    next.push({
      id: runId,
      thread_id: task.thread_id ?? "",
      title: task.feature_id ?? phaseName,
      phases: [],
      status: "running",
      started_at: new Date().toISOString(),
    });
    runIdx = next.length - 1;
  }

  const run = { ...next[runIdx]!, phases: next[runIdx]!.phases.slice() };
  next[runIdx] = run;

  let phaseIdx2 = run.phases.findIndex((p) => p.index === phaseIdx);
  if (phaseIdx2 === -1) {
    run.phases.push({ index: phaseIdx, name: phaseName, subagents: [] });
    run.phases.sort((a, b) => a.index - b.index);
    phaseIdx2 = run.phases.findIndex((p) => p.index === phaseIdx);
  }

  const phase = {
    ...run.phases[phaseIdx2]!,
    subagents: run.phases[phaseIdx2]!.subagents.slice(),
  };
  run.phases[phaseIdx2] = phase;

  const snap: SubagentSnap = {
    task_id: task.task_id,
    status: task.status,
    subagent_type: task.task_type ?? null,
    output_preview: task.message ?? null,
    error: task.error ?? null,
    token_usage: null,
    model_name: null,
  };

  const existing = phase.subagents.findIndex((s) => s.task_id === task.task_id);
  if (existing === -1) {
    phase.subagents.push(snap);
  } else {
    phase.subagents[existing] = { ...phase.subagents[existing]!, ...snap };
  }

  // Aggregate run status from all phases/subagents
  const allSubagents = run.phases.flatMap((p) => p.subagents);
  const allCompleted = allSubagents.every(
    (s) => s.status === "completed" || s.status === "success"
  );
  const anyFailed = allSubagents.some((s) => s.status === "failed");
  run.status = anyFailed
    ? "failed"
    : allCompleted
      ? "completed"
      : "running";

  return next;
}

export function reduceSubagentEvent(
  runs: Run[],
  ev: WorkspaceSubagentUpdatedEvent,
): Run[] {
  const sa = ev.subagent;
  const runId = sa.execution_session_id;
  const phaseIdx = asNumber(sa.workflow_phase_index) ?? 0;
  const phaseName = sa.workflow_phase ?? `phase ${phaseIdx}`;

  const next = runs.slice();
  let runIdx = next.findIndex((r) => r.id === runId);
  if (runIdx === -1) {
    next.push({
      id: runId,
      thread_id: sa.thread_id,
      title: phaseName,
      phases: [],
      status: "running",
      started_at: ev.timestamp ?? new Date().toISOString(),
    });
    runIdx = next.length - 1;
  }

  const run = { ...next[runIdx]!, phases: next[runIdx]!.phases.slice() };
  next[runIdx] = run;

  let phaseIdx2 = run.phases.findIndex((p) => p.index === phaseIdx);
  if (phaseIdx2 === -1) {
    run.phases.push({ index: phaseIdx, name: phaseName, subagents: [] });
    run.phases.sort((a, b) => a.index - b.index);
    phaseIdx2 = run.phases.findIndex((p) => p.index === phaseIdx);
  }

  const phase = { ...run.phases[phaseIdx2]!, subagents: run.phases[phaseIdx2]!.subagents.slice() };
  run.phases[phaseIdx2] = phase;

  const snap: SubagentSnap = {
    task_id: sa.task_id,
    status: sa.status,
    subagent_type: sa.subagent_type ?? null,
    output_preview: sa.output_preview ?? null,
    output: sa.output ?? null,
    error: sa.error ?? null,
    token_usage: sa.token_usage
      ? { total: sa.token_usage.total_tokens }
      : null,
    model_name: sa.model_name ?? null,
  };

  const existing = phase.subagents.findIndex((s) => s.task_id === sa.task_id);
  if (existing === -1) {
    phase.subagents.push(snap);
  } else {
    phase.subagents[existing] = { ...phase.subagents[existing]!, ...snap };
  }

  return next;
}
