import { renderHook, act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ExecutionRecord } from "@/lib/api/types";
import { useExecutionStore } from "@/stores/execution-store";
import { useExecutionStreamV2 } from "@/hooks/useExecutionStreamV2";

// useExecutionStream is a side-effect hook that subscribes to SSE.
// Mock it so tests don't try to open real network connections.
vi.mock("@/hooks/useExecutionStream", () => ({
  useExecutionStream: vi.fn(),
}));

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

beforeEach(() => {
  useExecutionStore.getState().clear();
});

describe("useExecutionStreamV2", () => {
  it("returns empty phases when no execution", () => {
    const { result } = renderHook(() => useExecutionStreamV2("ws-1"));
    expect(result.current.phases).toEqual([]);
    expect(result.current.executionId).toBeNull();
    expect(result.current.record).toBeNull();
  });

  it("returns phases grouped by node.phase", () => {
    useExecutionStore.getState().upsertExecution(
      makeRecord({
        id: "exec-1",
        node_states: {
          "node-1": { status: "completed" },
          "node-2": { status: "running" },
        },
        graph_structure: {
          nodes: [
            { id: "node-1", type: "skill", label: "Search", phase: "research" },
            { id: "node-2", type: "skill", label: "Analyze", phase: "research" },
            { id: "node-3", type: "skill", label: "Write", phase: "drafting" },
          ],
          edges: [{ from: "node-1", to: "node-2" }],
        },
      }),
    );

    const { result } = renderHook(() =>
      useExecutionStreamV2("ws-1", "exec-1"),
    );

    expect(result.current.phases).toHaveLength(2);
    expect(result.current.phases[0]).toEqual({
      name: "research",
      index: 0,
      nodes: [
        { id: "node-1", type: "skill", label: "Search", phase: "research" },
        { id: "node-2", type: "skill", label: "Analyze", phase: "research" },
      ],
    });
    expect(result.current.phases[1]).toEqual({
      name: "drafting",
      index: 1,
      nodes: [
        { id: "node-3", type: "skill", label: "Write", phase: "drafting" },
      ],
    });
  });

  it("groups nodes without phase into 'default'", () => {
    useExecutionStore.getState().upsertExecution(
      makeRecord({
        id: "exec-1",
        node_states: {},
        graph_structure: {
          nodes: [{ id: "node-1", type: "skill", label: "Plan" }],
          edges: [],
        },
      }),
    );

    const { result } = renderHook(() =>
      useExecutionStreamV2("ws-1", "exec-1"),
    );

    expect(result.current.phases).toHaveLength(1);
    expect(result.current.phases[0]!.name).toBe("default");
    expect(result.current.phases[0]!.nodes).toHaveLength(1);
  });

  it("manages selectedNodeId state", () => {
    const { result } = renderHook(() => useExecutionStreamV2("ws-1"));

    expect(result.current.selectedNodeId).toBeNull();

    act(() => {
      result.current.selectNode("node-1");
    });
    expect(result.current.selectedNodeId).toBe("node-1");

    act(() => {
      result.current.selectNode(null);
    });
    expect(result.current.selectedNodeId).toBeNull();
  });

  it("returns executionId from store when not provided", () => {
    useExecutionStore.getState().upsertExecution(makeRecord({ id: "exec-1" }));

    const { result } = renderHook(() => useExecutionStreamV2("ws-1"));
    expect(result.current.executionId).toBe("exec-1");
  });

  it("prefers explicit executionId over store currentExecutionId", () => {
    useExecutionStore.getState().upsertExecution(
      makeRecord({ id: "exec-default" }),
    );
    useExecutionStore.getState().upsertExecution(
      makeRecord({
        id: "exec-explicit",
        node_states: { "n-1": { status: "running" } },
        graph_structure: {
          nodes: [{ id: "n-1", type: "skill", label: "X" }],
          edges: [],
        },
      }),
    );

    const { result } = renderHook(() =>
      useExecutionStreamV2("ws-1", "exec-explicit"),
    );

    expect(result.current.executionId).toBe("exec-explicit");
    expect(result.current.phases).toHaveLength(1);
    expect(result.current.phases[0]!.nodes[0]!.id).toBe("n-1");
  });
});
