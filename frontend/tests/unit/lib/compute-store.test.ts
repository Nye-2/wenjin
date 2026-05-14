import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGetWorkspaceComputeSessions = vi.fn();
const mockGetComputeProjection = vi.fn();

vi.mock("@/lib/api", () => ({
  getWorkspaceComputeSessions: (...args: unknown[]) =>
    mockGetWorkspaceComputeSessions(...args),
  getComputeProjection: (...args: unknown[]) => mockGetComputeProjection(...args),
}));

import type { ComputeProjection, ComputeSession, ExecutionRecord } from "@/lib/api";
import { useComputeStore } from "@/stores/compute";

function session(overrides: Partial<ComputeSession> = {}): ComputeSession {
  return {
    id: overrides.id ?? "compute-1",
    execution_id: overrides.execution_id ?? "execution-1",
    workspace_id: overrides.workspace_id ?? "workspace-1",
    user_id: overrides.user_id ?? "user-1",
    sandbox_session_id: overrides.sandbox_session_id ?? null,
    active_view: overrides.active_view ?? "runtime",
    ui_state: overrides.ui_state ?? {},
    created_at: overrides.created_at ?? "2026-04-28T00:00:00Z",
    updated_at: overrides.updated_at ?? "2026-04-28T00:00:00Z",
  };
}

function execution(overrides: Partial<ExecutionRecord> = {}): ExecutionRecord {
  return {
    id: overrides.id ?? "execution-1",
    user_id: overrides.user_id ?? "user-1",
    workspace_id: overrides.workspace_id ?? "workspace-1",
    execution_type: overrides.execution_type ?? "feature",
    workspace_type: overrides.workspace_type ?? "thesis",
    feature_id: overrides.feature_id ?? "thesis.deep_research",
    status: overrides.status ?? "running",
    params: overrides.params ?? {},
    node_states: overrides.node_states ?? {},
    artifact_ids: overrides.artifact_ids ?? [],
    next_actions: overrides.next_actions ?? [],
    child_execution_ids: overrides.child_execution_ids ?? [],
    progress: overrides.progress ?? 0,
    created_at: overrides.created_at ?? "2026-04-28T00:00:00Z",
    updated_at: overrides.updated_at ?? "2026-04-28T00:00:00Z",
    ...overrides,
  };
}

function projection(
  overrides: Partial<ComputeProjection> = {}
): ComputeProjection {
  const computeSession = overrides.compute_session ?? session();
  return {
    compute_session: computeSession,
    execution: overrides.execution ?? execution({
      id: computeSession.execution_id,
      workspace_id: computeSession.workspace_id,
    }),
    primary_task: overrides.primary_task ?? null,
    tasks: overrides.tasks ?? [],
    runtime_blocks: overrides.runtime_blocks ?? [],
    subagents: overrides.subagents ?? [],
    artifacts: overrides.artifacts ?? {},
    runtime_profile:
      overrides.runtime_profile ??
      {
        runtime_mode: "compute_workflow",
        requires_compute: true,
        requires_sandbox: false,
        allowed_subagents: [],
        max_subagents: 0,
        output_contract: "feature_result",
        review_gate: null,
      },
    sandbox:
      overrides.sandbox ??
      {
        session_id: computeSession.sandbox_session_id,
        status: computeSession.sandbox_session_id ? "bound" : "unbound",
        required: false,
        files: [],
        logs: [],
        file_count: 0,
        log_count: 0,
      },
    prism:
      overrides.prism ??
      {
        status: "unbound",
        project_id: null,
        url: null,
        main_file: null,
        target_files: [],
        file_changes: [],
        applied_file_changes: [],
        compile: {},
        items: [],
      },
    files: overrides.files ?? [],
    logs: overrides.logs ?? [],
    review_gate:
      overrides.review_gate ??
      {
        status: "clear",
        required: false,
        policy: null,
        next_actions: [],
        items: [],
        advisory_code: null,
      },
  };
}

function resetStore() {
  useComputeStore.setState({
    byWorkspace: {},
    projectionBySessionId: {},
    activeComputeSessionIdByWorkspace: {},
    isLoadingByWorkspace: {},
    isProjectionLoadingBySessionId: {},
  });
}

describe("compute store", () => {
  beforeEach(() => {
    resetStore();
    mockGetWorkspaceComputeSessions.mockReset();
    mockGetComputeProjection.mockReset();
  });

  it("hydrates workspace sessions and selects the first returned session", async () => {
    const first = session({ id: "compute-1" });
    const second = session({ id: "compute-2", execution_id: "execution-2" });
    mockGetWorkspaceComputeSessions.mockResolvedValueOnce({
      items: [first, second],
      count: 2,
    });

    await useComputeStore.getState().hydrateWorkspace("workspace-1", 5);

    expect(mockGetWorkspaceComputeSessions).toHaveBeenCalledWith("workspace-1", 5);
    expect(useComputeStore.getState().byWorkspace["workspace-1"]).toEqual([
      first,
      second,
    ]);
    expect(
      useComputeStore.getState().activeComputeSessionIdByWorkspace["workspace-1"]
    ).toBe("compute-1");
    expect(useComputeStore.getState().isLoadingByWorkspace["workspace-1"]).toBe(
      false
    );
  });

  it("upserts sessions by recency without stealing an existing active session", () => {
    const first = session({
      id: "compute-1",
      updated_at: "2026-04-28T00:00:00Z",
    });
    const newer = session({
      id: "compute-2",
      execution_id: "execution-2",
      updated_at: "2026-04-28T01:00:00Z",
    });

    useComputeStore.getState().upsertComputeSession("workspace-1", first);
    useComputeStore.getState().upsertComputeSession("workspace-1", newer);

    expect(
      useComputeStore
        .getState()
        .byWorkspace["workspace-1"].map((item) => item.id)
    ).toEqual(["compute-2", "compute-1"]);
    expect(
      useComputeStore.getState().activeComputeSessionIdByWorkspace["workspace-1"]
    ).toBe("compute-1");
  });

  it("fetches and stores a compute projection", async () => {
    const computeProjection = projection({
      compute_session: session({ id: "compute-1" }),
      tasks: [{ task_id: "task-1", status: "running" }],
    });
    mockGetComputeProjection.mockResolvedValueOnce(computeProjection);

    const result = await useComputeStore.getState().fetchProjection("compute-1");

    expect(mockGetComputeProjection).toHaveBeenCalledWith("compute-1");
    expect(result).toEqual(computeProjection);
    expect(useComputeStore.getState().projectionBySessionId["compute-1"]).toEqual(
      computeProjection
    );
    expect(
      useComputeStore.getState().isProjectionLoadingBySessionId["compute-1"]
    ).toBe(false);
  });
});
