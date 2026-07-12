import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MessageBlock } from "@/app/(workbench)/workspaces/[id]/components/MessageBlock";

describe("MessageBlock mission presentation", () => {
  it("renders the canonical Mission status line", () => {
    render(
      <MessageBlock
        block={{
          kind: "status_line",
          label: "研究任务已开始",
          run_id: "mission-1",
          tone: "info",
        }}
      />,
    );

    expect(screen.getByText("研究任务已开始")).toBeInTheDocument();
  });

  it("forwards a result-card follow-up to chat", () => {
    const onIntent = vi.fn();
    render(
      <MessageBlock
        block={{
          kind: "result_card",
          run_id: "mission-1",
          title: "研究空白梳理",
          tldr: "已形成三个候选方向。",
          findings: [],
          links: [],
          feedback: {
            question: "下一步怎么推进？",
            pills: [{ kind: "primary", label: "继续打磨", intent: "继续打磨第二个方向" }],
            allow_free_input: true,
          },
          stats: { duration_ms: 1200, subagents: 2, tokens: 800 },
        }}
        onIntent={onIntent}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "继续打磨" }));
    expect(onIntent).toHaveBeenCalledWith("继续打磨第二个方向", "result_card");
  });

  it("does not render the stale embedded review projection from chat history", () => {
    render(
      <MessageBlock
        block={{
          kind: "result_card",
          run_id: "mission-1",
          title: "研究空白梳理",
          tldr: "完整确认状态请以研究任务视图为准。",
          findings: [],
          links: [],
          review_items: [
            {
              id: "legacy-review-1",
              kind: "claim",
              title: "旧的待确认内容",
              summary: "这段嵌入式投影不应继续显示。",
              status: "pending",
            },
          ],
          feedback: { question: "下一步怎么推进？", pills: [], allow_free_input: true },
          stats: { duration_ms: 1200, subagents: 2, tokens: 800 },
        }}
      />,
    );

    expect(screen.queryByText("旧的待确认内容")).not.toBeInTheDocument();
    expect(screen.getByText("完整确认状态请以研究任务视图为准。")).toBeInTheDocument();
  });
});
