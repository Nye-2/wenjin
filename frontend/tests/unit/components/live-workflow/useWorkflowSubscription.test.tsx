import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";

import { useWorkflowSubscription } from "@/app/(workbench)/workspaces/[id]/components/live-workflow/useWorkflowSubscription";
import { useWorkflowStore } from "@/stores/workflow-store";
import type { WorkspaceSubagentUpdatedEvent } from "@/lib/api/types";

const subscribeWorkspaceEvents = vi.fn();
vi.mock("@/lib/api/streams", () => ({
  subscribeWorkspaceEvents: (...args: unknown[]) => subscribeWorkspaceEvents(...args),
}));

vi.mock("@/stores/workflow-store", () => ({
  useWorkflowStore: {
    getState: vi.fn(),
  },
}));

describe("useWorkflowSubscription", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    subscribeWorkspaceEvents.mockReturnValue(() => {});
  });

  it("ingests a subagent.updated event and the store reflects it (1 run added)", () => {
    const upsertSubagentEvent = vi.fn();
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      upsertSubagentEvent,
    } as unknown as ReturnType<typeof useWorkflowStore.getState>);

    let capturedOnEvent: ((event: WorkspaceSubagentUpdatedEvent) => void) | undefined;
    subscribeWorkspaceEvents.mockImplementation((_workspaceId: string, onEvent: (event: WorkspaceSubagentUpdatedEvent) => void) => {
      capturedOnEvent = onEvent;
      return () => {};
    });

    renderHook(() => useWorkflowSubscription("ws-1"));

    const event: WorkspaceSubagentUpdatedEvent = {
      type: "subagent.updated",
      workspace_id: "ws-1",
      subagent: {
        task_id: "task-1",
        thread_id: "thread-1",
        execution_session_id: "run-1",
        status: "running",
        workflow_phase: "analysis",
        workflow_phase_index: 0,
      },
    };

    capturedOnEvent!(event);
    expect(upsertSubagentEvent).toHaveBeenCalledWith(event);
  });

  it("re-renders with same workspaceId don't re-subscribe (stable hook contract)", () => {
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      upsertSubagentEvent: vi.fn(),
    } as unknown as ReturnType<typeof useWorkflowStore.getState>);

    const { rerender } = renderHook(() => useWorkflowSubscription("ws-1"));
    rerender();
    expect(subscribeWorkspaceEvents).toHaveBeenCalledTimes(1);
  });

  it("unmount triggers the unsubscribe function", () => {
    const unsubscribe = vi.fn();
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      upsertSubagentEvent: vi.fn(),
    } as unknown as ReturnType<typeof useWorkflowStore.getState>);

    subscribeWorkspaceEvents.mockReturnValue(unsubscribe);

    const { unmount } = renderHook(() => useWorkflowSubscription("ws-1"));
    unmount();
    expect(unsubscribe).toHaveBeenCalledTimes(1);
  });
});
