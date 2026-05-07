import { beforeEach, describe, expect, it } from "vitest";

import type { WorkspaceSubagentUpdatedEvent } from "@/lib/api/types";
import { useWorkflowStore } from "@/stores/workflow-store";

const baseEv = (
  overrides: Partial<WorkspaceSubagentUpdatedEvent["subagent"]> = {},
): WorkspaceSubagentUpdatedEvent => ({
  type: "subagent.updated",
  workspace_id: "ws1",
  subagent: {
    task_id: "t1",
    thread_id: "th1",
    execution_session_id: "r1",
    status: "running",
    workflow_phase: "p1",
    workflow_phase_index: 0,
    workflow_task_index: 0,
    output_preview: null,
    ...overrides,
  },
});

function resetStore() {
  useWorkflowStore.setState({
    runs: [],
    currentRunId: null,
    pausedRunIds: new Set(),
    followCurrent: true,
    collapsedPhaseIds: new Set(),
    collapsedRunIds: new Set(),
  });
}

describe("workflow store · subagent.updated reducer", () => {
  beforeEach(resetStore);

  it("first event creates run + phase + subagent", () => {
    useWorkflowStore.getState().upsertSubagentEvent(baseEv());
    const { runs, currentRunId } = useWorkflowStore.getState();
    expect(runs).toHaveLength(1);
    expect(runs[0]!.id).toBe("r1");
    expect(runs[0]!.phases).toHaveLength(1);
    expect(runs[0]!.phases[0]!.subagents).toHaveLength(1);
    expect(runs[0]!.phases[0]!.subagents[0]!.task_id).toBe("t1");
    expect(currentRunId).toBe("r1");
  });

  it("updates existing subagent in place when status changes", () => {
    const s = useWorkflowStore.getState();
    s.upsertSubagentEvent(baseEv());
    s.upsertSubagentEvent(baseEv({ status: "completed", output_preview: "done" }));
    const sub = useWorkflowStore.getState().runs[0]!.phases[0]!.subagents[0]!;
    expect(sub.status).toBe("completed");
    expect(sub.output_preview).toBe("done");
  });

  it("groups by phase_index, preserves order", () => {
    const s = useWorkflowStore.getState();
    s.upsertSubagentEvent(baseEv({ task_id: "a", workflow_phase_index: 0 }));
    s.upsertSubagentEvent(
      baseEv({ task_id: "b", workflow_phase_index: 1, workflow_phase: "p2" }),
    );
    const phases = useWorkflowStore.getState().runs[0]!.phases;
    expect(phases).toHaveLength(2);
    expect(phases[0]!.subagents[0]!.task_id).toBe("a");
    expect(phases[1]!.subagents[0]!.task_id).toBe("b");
  });

  it("coerces stringified phase_index to number", () => {
    useWorkflowStore.getState().upsertSubagentEvent(
      baseEv({ workflow_phase_index: "2" }),
    );
    expect(useWorkflowStore.getState().runs[0]!.phases[0]!.index).toBe(2);
  });

  it("multiple subagents in same phase appear together in order", () => {
    const s = useWorkflowStore.getState();
    s.upsertSubagentEvent(baseEv({ task_id: "a", workflow_task_index: 0 }));
    s.upsertSubagentEvent(baseEv({ task_id: "b", workflow_task_index: 1 }));
    const subs = useWorkflowStore.getState().runs[0]!.phases[0]!.subagents;
    expect(subs.map((s) => s.task_id)).toEqual(["a", "b"]);
  });
});

describe("workflow store · UI toggles", () => {
  beforeEach(resetStore);

  it("toggleRun adds and removes from collapsedRunIds", () => {
    const s = useWorkflowStore.getState();
    s.upsertSubagentEvent(baseEv());
    s.toggleRun("r1");
    expect(useWorkflowStore.getState().collapsedRunIds.has("r1")).toBe(true);
    s.toggleRun("r1");
    expect(useWorkflowStore.getState().collapsedRunIds.has("r1")).toBe(false);
  });

  it("togglePhase keys by run+index", () => {
    const s = useWorkflowStore.getState();
    s.togglePhase("r1", 0);
    expect(useWorkflowStore.getState().collapsedPhaseIds.has("r1:0")).toBe(true);
    s.togglePhase("r1", 1);
    expect(useWorkflowStore.getState().collapsedPhaseIds.has("r1:1")).toBe(true);
    expect(useWorkflowStore.getState().collapsedPhaseIds.has("r1:0")).toBe(true);
    s.togglePhase("r1", 0);
    expect(useWorkflowStore.getState().collapsedPhaseIds.has("r1:0")).toBe(false);
  });

  it("setFollow flips followCurrent", () => {
    useWorkflowStore.getState().setFollow(false);
    expect(useWorkflowStore.getState().followCurrent).toBe(false);
    useWorkflowStore.getState().setFollow(true);
    expect(useWorkflowStore.getState().followCurrent).toBe(true);
  });
});
