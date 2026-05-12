import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { ChatPanel } from "@/app/(workbench)/workspaces/[id]/components/ChatPanel";
import { useChatStoreV2 } from "@/stores/chat-store";

beforeEach(() => {
  useChatStoreV2.getState().reset();
});

describe("ChatPanel v2", () => {
  it("renders empty state with input placeholder", () => {
    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("输入消息...")).toBeInTheDocument();
  });

  it("renders user messages with gray bubble", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.user.message",
      data: { id: "u1", content: "Hello", timestamp: "2026-01-01" },
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("renders text blocks inline in arrival order", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({
      type: "chat.assistant.block",
      block: { kind: "text", content: "first" },
    });
    handleEvent({
      type: "chat.assistant.block",
      block: { kind: "text", content: " second" },
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);
    expect(screen.getByText("first")).toBeInTheDocument();
    // The second text block has a leading space which is preserved in the DOM
    expect(screen.getByText(/second/)).toBeInTheDocument();
  });

  it("renders thinking blocks with collapsible toggle", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({ type: "chat.assistant.thinking", delta: "deep thought" });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);
    // Thinking toggle should be visible
    expect(screen.getByText("思考过程")).toBeInTheDocument();
  });

  it("renders tool invocation blocks", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({
      type: "chat.assistant.tool_invocation",
      data: { tool: "launch_feature", args: {} },
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);
    expect(screen.getByText(/launch_feature/)).toBeInTheDocument();
  });

  it("renders status line blocks", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({
      type: "chat.assistant.block",
      block: { kind: "status_line", content: "Searching literature..." },
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);
    expect(screen.getByText("Searching literature...")).toBeInTheDocument();
  });

  it("renders tool result blocks", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({
      type: "chat.assistant.tool_result",
      data: { status: "success" },
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);
    expect(screen.getByText(/success/)).toBeInTheDocument();
  });

  it("renders question card blocks", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({
      type: "chat.assistant.block",
      block: {
        kind: "question_card",
        data: { question: "Which approach?" },
      },
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);
    expect(screen.getByText(/Which approach/)).toBeInTheDocument();
  });

  it("renders result card blocks", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({
      type: "execution.completed",
      data: {
        execution_id: "ex1",
        capability_name: "literature_search",
        status: "completed",
        outputs: [],
      },
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);
    expect(screen.getByText(/literature_search/)).toBeInTheDocument();
  });

  it("renders mixed block types in arrival order", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    // Thinking comes first
    handleEvent({ type: "chat.assistant.thinking", delta: "hmm" });
    // Then text
    handleEvent({
      type: "chat.assistant.block",
      block: { kind: "text", content: "Here is my answer" },
    });
    // Then a tool invocation
    handleEvent({
      type: "chat.assistant.tool_invocation",
      data: { tool: "search", args: {} },
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);
    expect(screen.getByText("思考过程")).toBeInTheDocument();
    expect(screen.getByText("Here is my answer")).toBeInTheDocument();
    expect(screen.getByText(/search/)).toBeInTheDocument();
  });
});
