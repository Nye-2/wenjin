import { beforeEach, describe, expect, it, vi } from "vitest";

const mockAuthorizedFetch = vi.fn();

vi.mock("@/lib/api/client", () => ({
  authorizedFetch: (...args: unknown[]) => mockAuthorizedFetch(...args),
}));

import { useChatStoreV2 } from "@/stores/chat-store";

// Reset store between tests
beforeEach(() => {
  useChatStoreV2.getState().reset();
  mockAuthorizedFetch.mockReset();
});

describe("chat store", () => {
  it("merges consecutive text blocks into one rendered block", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({
      type: "chat.assistant.block",
      block: { kind: "text", content: "hi " },
    });
    handleEvent({
      type: "chat.assistant.block",
      block: { kind: "text", content: "world" },
    });

    const msg = useChatStoreV2.getState().messages.at(-1)!;
    expect(msg.blocks).toEqual([{ kind: "text", content: "hi world" }]);
  });

  it("preserves thinking in arrival order, NOT prepended", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({ type: "chat.assistant.thinking", delta: "thought 1" });
    handleEvent({
      type: "chat.assistant.block",
      block: { kind: "text", content: "answer" },
    });
    handleEvent({ type: "chat.assistant.thinking", delta: " more" });

    const last = useChatStoreV2.getState().messages.at(-1)!;
    const kinds = last.blocks.map((b) => b.kind);
    expect(kinds).toEqual(["thinking", "text", "thinking"]);
  });

  it("merges consecutive thinking deltas into one block", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({ type: "chat.assistant.thinking", delta: "part1" });
    handleEvent({ type: "chat.assistant.thinking", delta: " part2" });

    const last = useChatStoreV2.getState().messages.at(-1)!;
    expect(last.blocks).toEqual([{ kind: "thinking", content: "part1 part2" }]);
  });

  it("handles user message event", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.user.message",
      data: { id: "u1", content: "hello", timestamp: "2026-01-01" },
    });

    const msg = useChatStoreV2.getState().messages.at(-1)!;
    expect(msg.role).toBe("user");
    expect(msg.blocks[0]).toEqual({ kind: "text", content: "hello" });
  });

  it("handles tool invocation and result events", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({
      type: "chat.assistant.tool_invocation",
      data: {
        tool: "launch_feature",
        args: { capability: "literature_search" },
      },
    });
    handleEvent({
      type: "chat.assistant.tool_result",
      data: { execution_id: "exec-1", status: "started" },
    });

    const msg = useChatStoreV2.getState().messages.at(-1)!;
    expect(msg.blocks[0].kind).toBe("tool_invocation");
    expect(msg.blocks[1].kind).toBe("tool_result");
  });

  it("keeps launch tool result when final blocks replace streamed text", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({
      type: "chat.assistant.tool_result",
      data: {
        execution_id: "exec-1",
        feature_id: "sci_literature_positioning",
        status: "launched",
      },
    });
    handleEvent({
      type: "chat.assistant.block",
      block: { kind: "text", content: "streamed text" },
    });
    handleEvent({
      type: "chat.assistant.finalize_block",
      block: { kind: "text", content: "final text" },
    });

    const msg = useChatStoreV2.getState().messages.at(-1)!;
    expect(msg.blocks).toEqual([
      {
        kind: "tool_result",
        data: {
          execution_id: "exec-1",
          feature_id: "sci_literature_positioning",
          status: "launched",
        },
      },
      { kind: "text", content: "final text" },
    ]);
  });

  it("appends result_card on execution.completed", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({
      type: "chat.assistant.block",
      block: { kind: "text", content: "done" },
    });
    handleEvent({ type: "chat.assistant.completion" });
    handleEvent({
      type: "execution.completed",
      data: {
        execution_id: "exec-1",
        capability_name: "literature_search",
        status: "completed",
        outputs: [],
      },
    });

    const msg = useChatStoreV2.getState().messages.at(-1)!;
    expect(msg.blocks.at(-1)!.kind).toBe("result_card");
  });

  it("anchors result_card to the assistant message that owns the execution_id", () => {
    useChatStoreV2.setState({
      messages: [
        {
          id: "m-old",
          role: "assistant",
          blocks: [{ kind: "text", content: "earlier" }],
          createdAt: "2026-01-01",
          metadata: {
            orchestration: {
              execution_id: "exec-1",
            },
          },
        },
        {
          id: "m-new",
          role: "assistant",
          blocks: [{ kind: "text", content: "later" }],
          createdAt: "2026-01-02",
        },
      ],
      currentAssistantId: null,
      isSending: false,
      finalizedMessageIds: new Set<string>(),
    });

    useChatStoreV2.getState().handleEvent({
      type: "execution.completed",
      data: {
        execution_id: "exec-1",
        capability_name: "literature_search",
        status: "completed",
        outputs: [],
      },
    });

    const messages = useChatStoreV2.getState().messages;
    expect(messages[0].blocks.at(-1)!.kind).toBe("result_card");
    expect(messages[1].blocks.at(-1)!.kind).toBe("text");
  });

  it("handles completion event", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({ type: "chat.assistant.completion" });

    expect(useChatStoreV2.getState().currentAssistantId).toBeNull();
  });

  it("reset clears all state", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.user.message",
      data: { id: "u1", content: "hi", timestamp: "2026-01-01" },
    });
    useChatStoreV2.getState().reset();

    expect(useChatStoreV2.getState().messages).toEqual([]);
    expect(useChatStoreV2.getState().currentAssistantId).toBeNull();
  });

  it("loads history independently per workspace instead of reusing existing messages", async () => {
    mockAuthorizedFetch
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "thread-a",
            messages: [
              {
                id: "a-user",
                role: "user",
                content: "workspace A question",
                created_at: "2026-01-01",
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "thread-b",
            messages: [
              {
                id: "b-user",
                role: "user",
                content: "workspace B question",
                created_at: "2026-01-02",
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

    useChatStoreV2.getState().setActiveWorkspace("ws-a");
    await expect(useChatStoreV2.getState().loadHistory("ws-a")).resolves.toBe("thread-a");

    useChatStoreV2.getState().setActiveWorkspace("ws-b");
    await expect(useChatStoreV2.getState().loadHistory("ws-b")).resolves.toBe("thread-b");

    expect(mockAuthorizedFetch).toHaveBeenCalledTimes(2);
    expect(useChatStoreV2.getState().getWorkspaceMessages("ws-a")[0].blocks[0]).toEqual({
      kind: "text",
      content: "workspace A question",
    });
    expect(useChatStoreV2.getState().getWorkspaceMessages("ws-b")[0].blocks[0]).toEqual({
      kind: "text",
      content: "workspace B question",
    });
    expect(useChatStoreV2.getState().messages[0].blocks[0]).toEqual({
      kind: "text",
      content: "workspace B question",
    });
  });

  it("forwards seeded skill and orchestration metadata to thread creation and run launch", async () => {
    const encoder = new TextEncoder();
    mockAuthorizedFetch
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "thread-1", messages: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(encoder.encode("event: end\ndata: null\n\n"));
              controller.close();
            },
          }),
          {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          },
        ),
      );

    await useChatStoreV2.getState().sendMessage(
      "ws-1",
      "请帮我开始「论文分析」。论文标题：联邦学习+大模型",
      [],
      {
        skill: "paper-analyst",
        metadata: {
          orchestration: {
            feature_id: "paper_analysis",
            params: {
              paper_title: "联邦学习+大模型",
            },
          },
        },
      },
    );

    expect(mockAuthorizedFetch).toHaveBeenCalledTimes(2);
    expect(mockAuthorizedFetch).toHaveBeenNthCalledWith(
      1,
      "/api/workspaces/ws-1/thread",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skill: "paper-analyst" }),
      }),
    );

    expect(mockAuthorizedFetch).toHaveBeenNthCalledWith(
      2,
      "/api/threads/thread-1/runs/stream",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
    const runRequest = mockAuthorizedFetch.mock.calls[1]?.[1] as
      | RequestInit
      | undefined;
    expect(runRequest).toBeDefined();
    const runBody = JSON.parse(String(runRequest?.body ?? "{}")) as Record<
      string,
      unknown
    >;
    expect(runBody.skill).toBe("paper-analyst");
    expect(runBody.metadata).toEqual({
      orchestration: {
        feature_id: "paper_analysis",
        params: {
          paper_title: "联邦学习+大模型",
        },
      },
    });
  });
});
