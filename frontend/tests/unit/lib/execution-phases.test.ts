import { describe, expect, it } from "vitest";

import type { ExecutionRecord } from "@/lib/api/types";
import { groupExecutionPhases } from "@/lib/execution-phases";

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

describe("groupExecutionPhases", () => {
  it("returns empty phases when no graph exists", () => {
    expect(groupExecutionPhases(null)).toEqual([]);
    expect(groupExecutionPhases(makeRecord())).toEqual([]);
  });

  it("groups nodes by node.phase in first-seen order", () => {
    const record = makeRecord({
      graph_structure: {
        nodes: [
          { id: "node-1", type: "skill", label: "Search", phase: "research" },
          { id: "node-2", type: "skill", label: "Analyze", phase: "research" },
          { id: "node-3", type: "skill", label: "Write", phase: "drafting" },
        ],
        edges: [{ from: "node-1", to: "node-2" }],
      },
    });

    expect(groupExecutionPhases(record)).toEqual([
      {
        name: "research",
        index: 0,
        nodes: [
          { id: "node-1", type: "skill", label: "Search", phase: "research" },
          { id: "node-2", type: "skill", label: "Analyze", phase: "research" },
        ],
      },
      {
        name: "drafting",
        index: 1,
        nodes: [
          { id: "node-3", type: "skill", label: "Write", phase: "drafting" },
        ],
      },
    ]);
  });

  it("groups nodes without phase into default", () => {
    const record = makeRecord({
      graph_structure: {
        nodes: [{ id: "node-1", type: "skill", label: "Plan" }],
        edges: [],
      },
    });

    expect(groupExecutionPhases(record)).toEqual([
      {
        name: "default",
        index: 0,
        nodes: [{ id: "node-1", type: "skill", label: "Plan" }],
      },
    ]);
  });
});
