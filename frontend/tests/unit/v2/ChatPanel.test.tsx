import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { ChatPanel } from "@/app/(workbench)/workspaces/[id]/components/ChatPanel";
import { useChatStoreV2 } from "@/stores/chat-store";

const mockUseSearchParams = vi.fn(() => new URLSearchParams());

vi.mock("next/navigation", () => ({
  useSearchParams: () => mockUseSearchParams(),
}));

beforeEach(() => {
  useChatStoreV2.getState().reset();
  mockUseSearchParams.mockReturnValue(new URLSearchParams());
});

describe("ChatPanel v2", () => {
  it("renders empty state with input placeholder", () => {
    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("输入消息... Shift+Enter 换行"),
    ).toBeInTheDocument();
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
    expect(screen.getByText("first second")).toBeInTheDocument();
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

  it("auto-launches a seeded workspace entry once history is confirmed empty", async () => {
    const loadHistory = vi.fn().mockResolvedValue(null);
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({
      loadHistory,
      sendMessage,
      messages: [],
      isSending: false,
    });
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams({
        feature: "paper_analysis",
        skill: "paper-analyst",
        entry: "open",
        paper_title: "联邦学习+大模型",
        paper_abstract: "研究联邦场景下的大模型协同训练。",
      }),
    );

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);

    await waitFor(() => expect(loadHistory).toHaveBeenCalledWith("ws-1"));
    await waitFor(() =>
      expect(sendMessage).toHaveBeenCalledWith(
        "ws-1",
        expect.stringContaining("联邦学习+大模型"),
        [],
        {
          skill: "paper-analyst",
          metadata: expect.objectContaining({
            orchestration: expect.objectContaining({
              feature_id: "paper_analysis",
              params: expect.objectContaining({
                paper_title: "联邦学习+大模型",
                paper_abstract: "研究联邦场景下的大模型协同训练。",
                entry: "open",
              }),
            }),
          }),
        },
      ),
    );
  });

  it("forwards resume seed metadata on the first manual send without auto-launching", async () => {
    const loadHistory = vi.fn().mockResolvedValue("thread-1");
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({
      loadHistory,
      sendMessage,
      messages: [],
      isSending: false,
    });
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams({
        feature: "paper_analysis",
        skill: "paper-analyst",
        entry: "resume",
        execution_id: "exec-123",
        paper_title: "联邦学习+大模型",
      }),
    );

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);

    await waitFor(() => expect(loadHistory).toHaveBeenCalledWith("ws-1"));
    await waitFor(() => expect(sendMessage).not.toHaveBeenCalled());

    const input = screen.getByPlaceholderText("输入消息... Shift+Enter 换行");
    fireEvent.change(input, { target: { value: "继续完善这一轮分析" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter", shiftKey: false });

    await waitFor(() =>
      expect(sendMessage).toHaveBeenCalledWith(
        "ws-1",
        "继续完善这一轮分析",
        [],
        {
          skill: "paper-analyst",
          metadata: expect.objectContaining({
            orchestration: expect.objectContaining({
              feature_id: "paper_analysis",
              entry: "resume",
              execution_id: "exec-123",
              params: expect.objectContaining({
                paper_title: "联邦学习+大模型",
                execution_id: "exec-123",
              }),
            }),
          }),
        },
      ),
    );
  });
});
