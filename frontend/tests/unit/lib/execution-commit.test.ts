import { describe, expect, it } from "vitest";

import {
  type ExecutionCommitState,
  isExecutionReverted,
  readCommitStateFromResult,
  resolveExecutionCommitState,
} from "@/lib/execution-commit";

const COMMITTED_STATE: ExecutionCommitState = {
  status: "committed",
  accepted_ids: ["doc-1"],
  rejected_ids: [],
  counts: {
    library: 0,
    prism: 1,
    memory: 0,
    decisions: 0,
    tasks: 0,
    sandbox: 0,
    settings: 0,
  },
  room_targets: {
    prism: [{ output_id: "doc-1", item_id: "asset-1" }],
    library: [],
    memory: [],
    decisions: [],
    tasks: [],
    sandbox: [],
    settings: [],
  },
  committed_at: "2026-06-29T00:00:00Z",
};

const REVERTED_STATE: ExecutionCommitState = {
  ...COMMITTED_STATE,
  status: "reverted",
  reverted_at: "2026-06-29T00:01:00Z",
  reverted_by: "user-1",
  revert_counts: {
    library: 0,
    prism: 1,
    memory: 0,
    decisions: 0,
    tasks: 0,
    sandbox: 0,
    settings: 0,
  },
};

describe("execution-commit", () => {
  it("parses reverted commit state with revert counts", () => {
    const state = readCommitStateFromResult({
      commit_state: REVERTED_STATE,
    });

    expect(state?.status).toBe("reverted");
    expect(isExecutionReverted(state)).toBe(true);
    expect(state?.revert_counts?.prism).toBe(1);
  });

  it("parses sandbox and settings materialization targets", () => {
    const state = readCommitStateFromResult({
      commit_state: {
        ...COMMITTED_STATE,
        accepted_ids: ["unit-sandbox-1", "unit-settings-1"],
        counts: {
          ...COMMITTED_STATE.counts,
          sandbox: 1,
          settings: 1,
        },
        room_targets: {
          ...COMMITTED_STATE.room_targets,
          sandbox: [{ output_id: "unit-sandbox-1", item_id: "artifact-1" }],
          settings: [{ output_id: "unit-settings-1", item_id: "ws-1" }],
        },
      },
    });

    expect(state?.counts.sandbox).toBe(1);
    expect(state?.counts.settings).toBe(1);
    expect(state?.room_targets.sandbox[0]?.item_id).toBe("artifact-1");
    expect(state?.room_targets.settings[0]?.item_id).toBe("ws-1");
  });

  it("resolves local commit responses before durable or fallback state", () => {
    expect(
      resolveExecutionCommitState({
        localCommitState: REVERTED_STATE,
        durableCommitState: COMMITTED_STATE,
      })?.status,
    ).toBe("reverted");
  });

  it("falls back to durable then initial commit state when no local response exists", () => {
    expect(
      resolveExecutionCommitState({
        durableCommitState: COMMITTED_STATE,
        fallbackCommitState: REVERTED_STATE,
      })?.status,
    ).toBe("committed");
    expect(
      resolveExecutionCommitState({
        fallbackCommitState: REVERTED_STATE,
      })?.status,
    ).toBe("reverted");
  });
});
