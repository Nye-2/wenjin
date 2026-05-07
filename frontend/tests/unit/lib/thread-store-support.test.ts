import { describe, expect, it } from "vitest";

import type { AgentBlock } from "@/lib/api/blocks";
import {
  appendAgentBlock,
  createPendingUserMessage,
  createPlaceholderAssistantMessage,
  toChatMessages,
  type Message,
} from "@/stores/thread-store-support";

const text = (content: string): AgentBlock => ({ kind: "text", content });
const status = (run_id: string, label: string): AgentBlock => ({
  kind: "status_line",
  label,
  run_id,
  tone: "info",
});
const result = (run_id: string): AgentBlock => ({
  kind: "result_card",
  run_id,
  title: "📑 done",
  tldr: "x",
  findings: [],
  links: [],
  feedback: { question: "?", pills: [], allow_free_input: true },
  stats: { duration_ms: 1, subagents: 1, tokens: 1 },
});

describe("appendAgentBlock", () => {
  it("rekeys trailing pending assistant placeholder to the incoming messageId", () => {
    const messages: Message[] = [
      createPendingUserMessage({
        id: "u1",
        content: "hi",
        createdAt: "2026-05-07T00:00:00Z",
      }),
      createPlaceholderAssistantMessage({
        id: "assistant-placeholder",
        createdAt: "2026-05-07T00:00:01Z",
      }),
    ];
    const next = appendAgentBlock(messages, "msg-1", text("hello back"));
    expect(next).toHaveLength(2);
    expect(next[1]!.id).toBe("msg-1");
    expect(next[1]!.pending).toBe(false);
    expect(next[1]!.agentBlocks).toEqual([text("hello back")]);
  });

  it("appends to existing message when messageId already present", () => {
    const seedMessages: Message[] = [
      createPendingUserMessage({
        id: "u1",
        content: "hi",
        createdAt: "2026-05-07T00:00:00Z",
      }),
      createPlaceholderAssistantMessage({
        id: "msg-1",
        createdAt: "2026-05-07T00:00:01Z",
      }),
    ];
    const afterFirst = appendAgentBlock(
      seedMessages,
      "msg-1",
      text("part one"),
    );
    const afterSecond = appendAgentBlock(
      afterFirst,
      "msg-1",
      status("r1", "phase 1"),
    );
    expect(afterSecond).toHaveLength(2);
    expect(afterSecond[1]!.id).toBe("msg-1");
    expect(afterSecond[1]!.agentBlocks).toEqual([
      text("part one"),
      status("r1", "phase 1"),
    ]);
    expect(afterSecond[1]!.run_id).toBe("r1");
  });

  it("creates new assistant message when no placeholder exists", () => {
    const messages: Message[] = [
      createPendingUserMessage({
        id: "u1",
        content: "hi",
        createdAt: "2026-05-07T00:00:00Z",
      }),
    ];
    const next = appendAgentBlock(messages, "msg-2", result("r1"));
    expect(next).toHaveLength(2);
    expect(next[1]!.id).toBe("msg-2");
    expect(next[1]!.role).toBe("assistant");
    expect(next[1]!.agentBlocks).toEqual([result("r1")]);
    expect(next[1]!.run_id).toBe("r1");
  });

  it("propagates run_id from a status_line block onto the message", () => {
    const messages: Message[] = [
      createPlaceholderAssistantMessage({
        id: "msg-1",
        createdAt: "2026-05-07T00:00:00Z",
      }),
    ];
    const next = appendAgentBlock(
      messages,
      "msg-1",
      status("r-42", "phase x"),
    );
    expect(next[0]!.run_id).toBe("r-42");
  });

  it("does not regress run_id once set, even if later block lacks run_id", () => {
    const messages: Message[] = [
      createPlaceholderAssistantMessage({
        id: "msg-1",
        createdAt: "2026-05-07T00:00:00Z",
      }),
    ];
    const afterStatus = appendAgentBlock(
      messages,
      "msg-1",
      status("r-7", "x"),
    );
    const afterText = appendAgentBlock(afterStatus, "msg-1", text("more"));
    expect(afterText[0]!.run_id).toBe("r-7");
  });
});

describe("toChatMessages", () => {
  it("produces an empty list for an empty input", () => {
    expect(toChatMessages([])).toEqual([]);
  });

  it("converts user message + agent message and propagates run_id forward", () => {
    const messages: Message[] = [
      {
        id: "u1",
        role: "user",
        content: "hi",
        created_at: "2026-05-07T00:00:00Z",
        blocks: [],
        metadata: null,
      },
      {
        id: "msg-1",
        role: "assistant",
        content: "",
        created_at: "2026-05-07T00:00:01Z",
        blocks: [],
        agentBlocks: [text("hello"), status("r1", "p1")],
        run_id: "r1",
        metadata: null,
      },
    ];
    const chat = toChatMessages(messages);
    expect(chat).toHaveLength(2);
    expect(chat[0]).toMatchObject({
      id: "u1",
      role: "user",
      run_id: "r1",
      text: "hi",
    });
    expect(chat[1]).toMatchObject({
      id: "msg-1",
      role: "agent",
      run_id: "r1",
      blocks: [text("hello"), status("r1", "p1")],
    });
  });

  it("synthesizes a TextBlock from legacy assistant.content when agentBlocks empty", () => {
    const messages: Message[] = [
      {
        id: "msg-legacy",
        role: "assistant",
        content: "legacy text",
        created_at: "2026-05-07T00:00:01Z",
        blocks: [],
        metadata: null,
      },
    ];
    const chat = toChatMessages(messages);
    expect(chat).toHaveLength(1);
    expect(chat[0]!.blocks).toEqual([text("legacy text")]);
  });

  it("skips empty pending placeholder assistant messages", () => {
    const messages: Message[] = [
      {
        id: "msg-pending",
        role: "assistant",
        content: "",
        created_at: "2026-05-07T00:00:01Z",
        blocks: [],
        metadata: null,
        pending: true,
      },
    ];
    expect(toChatMessages(messages)).toEqual([]);
  });

  it("falls back to local: run_id when no run id is known yet", () => {
    const messages: Message[] = [
      {
        id: "u-only",
        role: "user",
        content: "x",
        created_at: "2026-05-07T00:00:00Z",
        blocks: [],
        metadata: null,
      },
    ];
    const chat = toChatMessages(messages);
    expect(chat).toHaveLength(1);
    expect(chat[0]!.run_id).toMatch(/^local:/);
  });
});
