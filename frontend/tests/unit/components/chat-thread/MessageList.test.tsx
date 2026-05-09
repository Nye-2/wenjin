import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import {
  MessageList,
  type ChatMessage,
} from "@/app/(workbench)/workspaces/[id]/components/chat-thread/MessageList";

const msgs: ChatMessage[] = [
  { id: "u1", role: "user", run_id: "r1", text: "hi" },
  {
    id: "a1",
    role: "agent",
    run_id: "r1",
    blocks: [{ kind: "text", content: "好" }],
  },
  {
    id: "a2",
    role: "agent",
    run_id: "r1",
    blocks: [
      {
        kind: "result_card",
        run_id: "r1",
        title: "📑 完成",
        tldr: "TL;DR text",
        findings: [{ id: "1", text: "first finding" }],
        links: [],
        feedback: {
          question: "?",
          pills: [{ kind: "primary", label: "next", intent: "next" }],
          allow_free_input: true,
        },
        stats: { duration_ms: 1000, subagents: 1, tokens: 100 },
      },
    ],
  },
  { id: "u2", role: "user", run_id: "r2", text: "深入第 1" },
  {
    id: "a3",
    role: "agent",
    run_id: "r2",
    blocks: [{ kind: "text", content: "好的" }],
  },
];

describe("MessageList", () => {
  it("renders all messages in flat flow", () => {
    render(<MessageList messages={msgs} />);
    // All messages are visible (no run grouping / folding)
    expect(screen.getByText("hi")).toBeInTheDocument();
    expect(screen.getByText("好")).toBeInTheDocument();
    expect(screen.getByText("深入第 1")).toBeInTheDocument();
    expect(screen.getByText("好的")).toBeInTheDocument();
  });

  it("renders user bubble vs agent block-container distinctly", () => {
    render(<MessageList messages={msgs} />);
    expect(screen.getByText("深入第 1")).toBeInTheDocument();
  });

  it("clicking a question pill submits its intent", () => {
    const onSubmit = vi.fn();
    const m: ChatMessage[] = [
      {
        id: "a1",
        role: "agent",
        run_id: "r1",
        blocks: [
          {
            kind: "question_card",
            label: "需要你拍",
            question: "?",
            pills: [{ label: "选 A", intent: "select-a" }],
          },
        ],
      },
    ];
    render(
      <MessageList messages={m} onSubmit={onSubmit} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "选 A" }));
    expect(onSubmit).toHaveBeenCalledWith("select-a");
  });

  it("clicking a result_card feedback pill submits its intent", () => {
    const onSubmit = vi.fn();
    render(<MessageList messages={msgs} onSubmit={onSubmit} />);
    fireEvent.click(screen.getByRole("button", { name: "next" }));
    expect(onSubmit).toHaveBeenCalledWith("next");
  });

  it("threads onJumpToPhase down to status_line blocks", () => {
    const onJump = vi.fn();
    const m: ChatMessage[] = [
      {
        id: "a1",
        role: "agent",
        run_id: "r1",
        blocks: [
          {
            kind: "status_line",
            label: "phase 1 完成",
            run_id: "r1",
            phase_index: 1,
            tone: "info",
          },
        ],
      },
    ];
    render(
      <MessageList messages={m} onJumpToPhase={onJump} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /phase 1 完成/ }));
    expect(onJump).toHaveBeenCalledWith("r1", 1);
  });
});
