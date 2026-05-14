import { beforeEach, describe, expect, it } from "vitest";

import { useChatStoreV2 } from "@/stores/chat-store";

// Reset store between tests
beforeEach(() => {
  useChatStoreV2.getState().reset();
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
});
