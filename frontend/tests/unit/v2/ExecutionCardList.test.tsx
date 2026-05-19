import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ExecutionRecord } from "@/lib/api/types";
import { ExecutionCardList } from "@/app/(workbench)/workspaces/[id]/components/ExecutionCardList";
import { useExecutionStore } from "@/stores/execution-store";

function makeRecord(
  overrides: Partial<ExecutionRecord> = {},
): ExecutionRecord {
  return {
    id: "exec-1",
    user_id: "user-1",
    workspace_id: "ws-1",
    execution_type: "feature",
    workspace_type: "thesis",
    feature_id: "thesis_writing",
    status: "running",
    params: {},
    node_states: {},
    artifact_ids: [],
    next_actions: [],
    child_execution_ids: [],
    progress: 50,
    created_at: "2026-05-18T00:00:00Z",
    updated_at: "2026-05-18T00:00:05Z",
    ...overrides,
  };
}

describe("ExecutionCardList", () => {
  beforeEach(() => {
    useExecutionStore.getState().clear();
  });

  it("does not trigger React getSnapshot loop warnings when rendering execution cards", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    useExecutionStore.getState().upsertExecution(makeRecord());

    render(<ExecutionCardList workspaceId="ws-1" />);

    const joined = consoleError.mock.calls
      .flatMap((call) => call.map((item) => String(item)))
      .join("\n");
    expect(joined).not.toContain("getSnapshot should be cached");
    expect(joined).not.toContain("Maximum update depth exceeded");

    consoleError.mockRestore();
  });
});
