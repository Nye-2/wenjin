import { beforeEach, describe, expect, it } from "vitest";

import type { ExecutionRecord, ExecutionStreamEvent } from "@/lib/api/types";
import { useExecutionStore } from "@/stores/execution-store";

const makeRecord = (
  overrides: Partial<ExecutionRecord> = {},
): ExecutionRecord => ({
  id: "exec-1",
  user_id: "u1",
  execution_type: "feature",
  status: "running",
  params: {},
  node_states: {},
  artifact_ids: [],
  next_actions: [],
  child_execution_ids: [],
  progress: 0,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

const makeEvent = (
  overrides: Partial<ExecutionStreamEvent> = {},
): ExecutionStreamEvent => ({
  execution_id: "exec-1",
  type: "execution.status",
  timestamp: "2026-01-01T00:00:01Z",
  payload: {},
  ...overrides,
});

beforeEach(() => {
  useExecutionStore.getState().clear();
});

describe("execution-store", () => {
  it("uses execution.completed payload status and keeps failed_partial terminal", () => {
    useExecutionStore.getState().upsertExecution(makeRecord());

    useExecutionStore.getState().applyStreamEvent(
      makeEvent({
        type: "execution.completed",
        payload: {
          execution_id: "exec-1",
          capability_id: "lit_review",
          status: "failed_partial",
          duration_seconds: 12,
          narrative: "Completed with one failed node.",
          outputs: [
            {
              id: "paper-1",
              kind: "library_item",
              preview: "Paper preview",
              default_checked: true,
              data: { title: "Paper" },
            },
          ],
          errors: [{ phase: "search", task: "api", error: "429" }],
        },
      }),
    );

    useExecutionStore.getState().applyStreamEvent(
      makeEvent({
        type: "execution.end",
        timestamp: "2026-01-01T00:00:02Z",
      }),
    );

    const record = useExecutionStore.getState().executions.get("exec-1");
    expect(record?.status).toBe("failed_partial");
    expect(record?.result_summary).toBe("Completed with one failed node.");
    expect(record?.result?.outputs).toHaveLength(1);
  });

  it("appends thinking deltas instead of replacing them", () => {
    useExecutionStore.getState().upsertExecution(makeRecord());

    useExecutionStore.getState().applyStreamEvent(
      makeEvent({
        type: "execution.node.delta",
        payload: { node_id: "node-1", thinking: "hello " },
      }),
    );
    useExecutionStore.getState().applyStreamEvent(
      makeEvent({
        type: "execution.node.delta",
        payload: { node_id: "node-1", thinking: "world" },
      }),
    );

    const record = useExecutionStore.getState().executions.get("exec-1");
    expect(record?.node_states["node-1"]?.thinking).toBe("hello world");
  });
});
