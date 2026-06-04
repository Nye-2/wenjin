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
      block: {
        kind: "status_line",
        label: "Searching literature...",
        run_id: "run-1",
        tone: "info",
      },
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

  it("renders launch_feature lead-busy advisory as the busy state", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({
      type: "chat.assistant.tool_result",
      data: {
        status: "advisory",
        code: "lead_busy",
        detail: "Lead Agent 正在执行",
      },
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);
    expect(screen.getByText(/Lead Agent 仍在执行/)).toBeInTheDocument();
    expect(screen.queryByText("✓ advisory")).not.toBeInTheDocument();
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
        label: "需要你拍一下",
        question: "Which approach?",
        pills: [],
      },
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);
    expect(screen.getByText(/Which approach/)).toBeInTheDocument();
  });

  it("switches the placeholder when a blocking question card is present", () => {
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({
      type: "chat.assistant.block",
      block: {
        kind: "question_card",
        label: "需要你拍一下",
        question: "Which approach?",
        pills: [],
      },
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);

    expect(screen.getByPlaceholderText("直接说想法...")).toBeInTheDocument();
  });

  it("sends the canonical question card pill intent when clicked", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({
      sendMessage,
      isSending: false,
    });
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({
      type: "chat.assistant.block",
      block: {
        kind: "question_card",
        label: "需要你拍一下",
        question: "继续跳过这篇文献吗？",
        pills: [
          { label: "跳过", intent: "skip_this_paper" },
          { label: "我来上传 PDF", intent: "upload_pdf" },
        ],
      },
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);

    fireEvent.click(screen.getByRole("button", { name: "跳过" }));

    await waitFor(() =>
      expect(sendMessage).toHaveBeenCalledWith(
        "ws-1",
        "skip_this_paper",
        [],
        {
          metadata: {
            block_action: {
              action: "continue_thread",
              intent: "skip_this_paper",
              source_block_kind: "question_card",
            },
          },
        },
      ),
    );
  });

  it("preserves execution orchestration metadata when a question card pill continues the current run", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({
      messages: [
        {
          id: "m1",
          role: "assistant",
          createdAt: "2026-01-01",
          metadata: {
            orchestration: {
              execution_id: "exec-123",
            },
          },
          blocks: [
            {
              kind: "question_card",
              label: "需要你拍一下",
              question: "继续跳过这篇文献吗？",
              pills: [{ label: "跳过", intent: "skip_this_paper" }],
            },
          ],
        },
      ],
      sendMessage,
      isSending: false,
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);

    fireEvent.click(screen.getByRole("button", { name: "跳过" }));

    await waitFor(() =>
      expect(sendMessage).toHaveBeenCalledWith(
        "ws-1",
        "skip_this_paper",
        [],
        {
          metadata: {
            block_action: {
              action: "continue_thread",
              intent: "skip_this_paper",
              source_block_kind: "question_card",
            },
            orchestration: {
              execution_id: "exec-123",
            },
          },
        },
      ),
    );
  });

  it("renders canonical result cards and forwards feedback pill intents", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({
      sendMessage,
      isSending: false,
    });
    const { handleEvent } = useChatStoreV2.getState();
    handleEvent({
      type: "chat.assistant.start",
      data: { message_id: "m1", timestamp: "2026-01-01" },
    });
    handleEvent({
      type: "chat.assistant.finalize_block",
      block: {
        kind: "result_card",
        run_id: "run-1",
        title: "论文分析 已完成",
        tldr: "已经总结出三条主要贡献。",
        findings: [
          { id: "①", text: "提出了新的聚合策略" },
          { id: "②", text: "验证了跨域泛化能力" },
        ],
        links: [{ icon: "file", label: "阅读摘要", href: "/artifacts/art-1" }],
        feedback: {
          question: "接下来怎么做？",
          pills: [{ kind: "primary", label: "深入展开 ①", intent: "expand_finding_1" }],
          allow_free_input: true,
        },
        stats: {
          duration_ms: 12000,
          subagents: 2,
          tokens: 1800,
        },
      },
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);

    expect(screen.getByText("论文分析 已完成")).toBeInTheDocument();
    expect(screen.getByText("已经总结出三条主要贡献。")).toBeInTheDocument();
    expect(screen.getByText("提出了新的聚合策略")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "阅读摘要" })).toHaveAttribute(
      "href",
      "/artifacts/art-1",
    );

    fireEvent.click(screen.getByRole("button", { name: "深入展开 ①" }));

    await waitFor(() =>
      expect(sendMessage).toHaveBeenCalledWith(
        "ws-1",
        "expand_finding_1",
        [],
        {
          metadata: {
            block_action: {
              action: "continue_thread",
              intent: "expand_finding_1",
              source_block_kind: "result_card",
            },
          },
        },
      ),
    );
  });

  it("preserves execution orchestration metadata when a result card feedback pill iterates the same run", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({
      messages: [
        {
          id: "m1",
          role: "assistant",
          createdAt: "2026-01-01",
          metadata: {
            orchestration: {
              execution_id: "exec-456",
            },
          },
          blocks: [
            {
              kind: "result_card",
              run_id: "run-1",
              title: "论文分析 已完成",
              tldr: "已经总结出三条主要贡献。",
              findings: [{ id: "①", text: "提出了新的聚合策略" }],
              links: [],
              feedback: {
                question: "接下来怎么做？",
                pills: [{ kind: "primary", label: "深入展开 ①", intent: "expand_finding_1" }],
                allow_free_input: true,
              },
              stats: {
                duration_ms: 12000,
                subagents: 2,
                tokens: 1800,
              },
            },
          ],
        },
      ],
      sendMessage,
      isSending: false,
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);

    fireEvent.click(screen.getByRole("button", { name: "深入展开 ①" }));

    await waitFor(() =>
      expect(sendMessage).toHaveBeenCalledWith(
        "ws-1",
        "expand_finding_1",
        [],
        {
          metadata: {
            block_action: {
              action: "continue_thread",
              intent: "expand_finding_1",
              source_block_kind: "result_card",
            },
            orchestration: {
              execution_id: "exec-456",
            },
          },
        },
      ),
    );
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

  it("switches the placeholder when a result card is ready for feedback", () => {
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

    expect(
      screen.getByPlaceholderText("或对结果反馈、推翻、迭代"),
    ).toBeInTheDocument();
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

  it("auto-launches a seeded entry for an empty workspace even when another workspace has messages", async () => {
    const loadHistory = vi.fn().mockResolvedValue(null);
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({
      activeWorkspaceId: "ws-old",
      messagesByWorkspace: {
        "ws-old": [
          {
            id: "old-user",
            role: "user",
            blocks: [{ kind: "text", content: "old workspace message" }],
            createdAt: "2026-01-01",
          },
        ],
      },
      messages: [
        {
          id: "old-user",
          role: "user",
          blocks: [{ kind: "text", content: "old workspace message" }],
          createdAt: "2026-01-01",
        },
      ],
      loadHistory,
      sendMessage,
      isSending: false,
    });
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams({
        feature: "paper_analysis",
        skill: "paper-analyst",
        entry: "open",
        paper_title: "新工作区论文",
      }),
    );

    render(<ChatPanel workspaceId="ws-new" data-testid="chat-panel" />);

    expect(screen.queryByText("old workspace message")).not.toBeInTheDocument();
    await waitFor(() => expect(loadHistory).toHaveBeenCalledWith("ws-new"));
    await waitFor(() =>
      expect(sendMessage).toHaveBeenCalledWith(
        "ws-new",
        expect.stringContaining("新工作区论文"),
        [],
        expect.objectContaining({
          skill: "paper-analyst",
        }),
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

  it("does not submit while an IME composition is active", async () => {
    const loadHistory = vi.fn().mockResolvedValue(null);
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({
      loadHistory,
      sendMessage,
      messages: [],
      isSending: false,
    });

    render(<ChatPanel workspaceId="ws-1" data-testid="chat-panel" />);

    await waitFor(() => expect(loadHistory).toHaveBeenCalledWith("ws-1"));

    const input = screen.getByPlaceholderText("输入消息... Shift+Enter 换行");
    fireEvent.change(input, { target: { value: "aaai" } });
    fireEvent.compositionStart(input);
    fireEvent.keyDown(input, { key: "Enter", code: "Enter", shiftKey: false });

    expect(sendMessage).not.toHaveBeenCalled();

    fireEvent.compositionEnd(input);
    fireEvent.keyDown(input, { key: "Enter", code: "Enter", shiftKey: false });

    await waitFor(() =>
      expect(sendMessage).toHaveBeenCalledWith("ws-1", "aaai", [], undefined),
    );
  });
});
