import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkspaceEvent } from "@/lib/api/types";
import { useChatStoreV2 } from "@/stores/chat-store";
import { useExecutionStore } from "@/stores/execution-store";

const mockSubscribeWorkspaceEvents = vi.fn();
const mockUseExecutionStream = vi.fn();
const mockGetExecution = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    subscribeWorkspaceEvents: (...args: unknown[]) =>
      mockSubscribeWorkspaceEvents(...args),
  };
});

vi.mock("@/hooks/useExecutionStream", () => ({
  useExecutionStream: (executionId: string | null) =>
    mockUseExecutionStream(executionId),
}));

vi.mock("@/lib/api/executions", () => ({
  getExecution: (...args: unknown[]) => mockGetExecution(...args),
}));

import { useWorkspaceEventStream } from "@/hooks/useWorkspaceEventStream";

const makeExecutionRecord = () => ({
  id: "exec-1",
  user_id: "u1",
  workspace_id: "ws-1",
  execution_type: "feature" as const,
  feature_id: "lit_review",
  status: "completed" as const,
  params: {},
  result: {
    task_report: {
      execution_id: "exec-1",
      capability_id: "lit_review",
      status: "completed",
      duration_seconds: 4,
      narrative: "done",
      outputs: [],
      errors: [],
    },
  },
  node_states: {},
  artifact_ids: [],
  next_actions: [],
  child_execution_ids: [],
  progress: 100,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:04Z",
});

beforeEach(() => {
  useChatStoreV2.getState().reset();
  useExecutionStore.getState().clear();
  mockSubscribeWorkspaceEvents.mockReset();
  mockUseExecutionStream.mockReset();
  mockGetExecution.mockReset();
  mockSubscribeWorkspaceEvents.mockReturnValue(vi.fn());
});

describe("useWorkspaceEventStream", () => {
  it("is the single workspace SSE owner", () => {
    let onEvent: ((event: WorkspaceEvent) => void) | undefined;
    mockSubscribeWorkspaceEvents.mockImplementation((_workspaceId, handler) => {
      onEvent = handler as (event: WorkspaceEvent) => void;
      return vi.fn();
    });

    renderHook(() => useWorkspaceEventStream("ws-1"));

    expect(mockSubscribeWorkspaceEvents).toHaveBeenCalledTimes(1);
    expect(onEvent).toBeTypeOf("function");
  });

  it("subscribes to one execution stream and hydrates terminal records once", async () => {
    let onEvent: ((event: WorkspaceEvent) => void) | undefined;
    mockSubscribeWorkspaceEvents.mockImplementation((_workspaceId, handler) => {
      onEvent = handler as (event: WorkspaceEvent) => void;
      return vi.fn();
    });
    mockGetExecution.mockResolvedValue(makeExecutionRecord());

    const { rerender } = renderHook(() => useWorkspaceEventStream("ws-1"));
    useChatStoreV2.getState().handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "assistant-1" },
    });
    useChatStoreV2.getState().handleEvent({ type: "chat.assistant.completion" });

    act(() => {
      onEvent?.({
        type: "execution.updated",
        workspace_id: "ws-1",
        execution_id: "exec-1",
        event_type: "execution.status",
        status: "running",
      });
    });
    rerender();

    expect(mockUseExecutionStream).toHaveBeenLastCalledWith("exec-1");
    await waitFor(() => {
      expect(useExecutionStore.getState().executions.get("exec-1")).toBeDefined();
    });

    act(() => {
      onEvent?.({
        type: "execution.updated",
        workspace_id: "ws-1",
        execution_id: "exec-1",
        event_type: "execution.completed",
        status: "completed",
      });
    });

    await waitFor(() => {
      const message = useChatStoreV2.getState().messages.at(-1);
      expect(message?.blocks.at(-1)?.kind).toBe("result_card");
    });

    act(() => {
      onEvent?.({
        type: "execution.updated",
        workspace_id: "ws-1",
        execution_id: "exec-1",
        event_type: "execution.completed",
        status: "completed",
      });
    });

    await Promise.resolve();
    const resultCards = useChatStoreV2
      .getState()
      .messages.flatMap((message) =>
        message.blocks.filter((block) => block.kind === "result_card"),
      );
    expect(resultCards).toHaveLength(1);
  });
});
