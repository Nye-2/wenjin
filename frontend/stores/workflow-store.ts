/**
 * Workflow store · Plan 2 T3.
 *
 * Subscribes to `subagent.updated` SSE events (via Plan 2 T8 hook) and
 * reduces them into a `Run -> Phase -> Subagent` tree consumed by the
 * LiveWorkflowPanel. Also exposes UI-state toggles (collapsed runs/phases,
 * follow-current) and lifecycle action wrappers (pause/resume/delete) that
 * call the run-scoped HTTP endpoints from Plan 1 T10 / T15.
 */
import { create } from "zustand";

import {
  deleteWorkspaceRun as apiDeleteRun,
  pauseRunLifecycle as apiPause,
  resumeRunLifecycle as apiResume,
} from "@/lib/api/runs";
import type { WorkspaceSubagentUpdatedEvent } from "@/lib/api/types";

import { type Run, reduceSubagentEvent } from "./workflow-store-support";

interface WorkflowState {
  runs: Run[];
  currentRunId: string | null;
  pausedRunIds: Set<string>;
  followCurrent: boolean;
  collapsedPhaseIds: Set<string>; // key = `${runId}:${phaseIndex}`
  collapsedRunIds: Set<string>;

  upsertSubagentEvent: (ev: WorkspaceSubagentUpdatedEvent) => void;
  toggleRun: (runId: string) => void;
  togglePhase: (runId: string, phaseIndex: number) => void;
  setFollow: (enabled: boolean) => void;
  pauseRun: (runId: string) => Promise<void>;
  resumeRun: (runId: string) => Promise<void>;
  deleteRun: (runId: string) => Promise<void>;
}

export const useWorkflowStore = create<WorkflowState>((set) => ({
  runs: [],
  currentRunId: null,
  pausedRunIds: new Set<string>(),
  followCurrent: true,
  collapsedPhaseIds: new Set<string>(),
  collapsedRunIds: new Set<string>(),

  upsertSubagentEvent(ev) {
    set((state) => {
      const runs = reduceSubagentEvent(state.runs, ev);
      return { runs, currentRunId: ev.subagent.execution_session_id };
    });
  },

  toggleRun(runId) {
    set((s) => {
      const next = new Set(s.collapsedRunIds);
      if (next.has(runId)) next.delete(runId);
      else next.add(runId);
      return { collapsedRunIds: next };
    });
  },

  togglePhase(runId, phaseIndex) {
    const key = `${runId}:${phaseIndex}`;
    set((s) => {
      const next = new Set(s.collapsedPhaseIds);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return { collapsedPhaseIds: next };
    });
  },

  setFollow(enabled) {
    set({ followCurrent: enabled });
  },

  async pauseRun(runId) {
    await apiPause(runId);
    set((s) => ({ pausedRunIds: new Set([...s.pausedRunIds, runId]) }));
  },

  async resumeRun(runId) {
    await apiResume(runId);
    set((s) => {
      const next = new Set(s.pausedRunIds);
      next.delete(runId);
      return { pausedRunIds: next };
    });
  },

  async deleteRun(runId) {
    await apiDeleteRun(runId);
    set((s) => ({ runs: s.runs.filter((r) => r.id !== runId) }));
  },
}));
