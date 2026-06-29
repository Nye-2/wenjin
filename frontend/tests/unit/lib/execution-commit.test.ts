import { describe, expect, it } from "vitest";

import {
  isExecutionReverted,
  readCommitStateFromResult,
} from "@/lib/execution-commit";

describe("execution-commit", () => {
  it("parses reverted commit state with revert counts", () => {
    const state = readCommitStateFromResult({
      commit_state: {
        status: "reverted",
        accepted_ids: ["doc-1"],
        rejected_ids: [],
        counts: { library: 0, prism: 1, memory: 0, decisions: 0, tasks: 0 },
        room_targets: {
          prism: [{ output_id: "doc-1", item_id: "asset-1" }],
          library: [],
          memory: [],
          decisions: [],
          tasks: [],
        },
        committed_at: "2026-06-29T00:00:00Z",
        reverted_at: "2026-06-29T00:01:00Z",
        reverted_by: "user-1",
        revert_counts: {
          library: 0,
          prism: 1,
          memory: 0,
          decisions: 0,
          tasks: 0,
        },
      },
    });

    expect(state?.status).toBe("reverted");
    expect(isExecutionReverted(state)).toBe(true);
    expect(state?.revert_counts?.prism).toBe(1);
  });
});
