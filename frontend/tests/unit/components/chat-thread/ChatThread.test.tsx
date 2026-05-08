import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

import { ChatThread } from "@/app/(workbench)/workspaces/[id]/components/chat-thread/ChatThread";
import { useWorkflowStore } from "@/stores/workflow-store";

function resetStore() {
  useWorkflowStore.setState({
    runs: [],
    currentRunId: null,
    pausedRunIds: new Set(),
    followCurrent: true,
    collapsedPhaseIds: new Set(),
    collapsedRunIds: new Set(),
  });
}

describe("ChatThread", () => {
  beforeEach(resetStore);

  it("renders EmptyState when there are no messages", () => {
    render(
      <ChatThread
        workspaceId="ws1"
        messages={[]}
        feature={{
          id: "paper_analysis",
          name: "论文分析",
          description: "拆解论文方法、实验、结论",
        }}
        starterPrompts={["start a", "start b", "start c"]}
      />,
    );
    expect(screen.getByText(/论文分析/)).toBeInTheDocument();
    expect(screen.getByText("start a")).toBeInTheDocument();
  });

  it("renders MessageList when there are messages", () => {
    render(
      <ChatThread
        workspaceId="ws1"
        messages={[{ id: "u", role: "user", run_id: "r1", text: "hi" }]}
        feature={null}
        starterPrompts={[]}
      />,
    );
    expect(screen.getByText("hi")).toBeInTheDocument();
  });

  it("input placeholder reflects whether a run is in flight", () => {
    // No active run
    const { rerender } = render(
      <ChatThread
        workspaceId="ws1"
        messages={[]}
        feature={null}
        starterPrompts={[]}
      />,
    );
    expect(screen.getByPlaceholderText(/输入开始对话/)).toBeInTheDocument();

    // Active run — store drives the placeholder
    useWorkflowStore.setState({ currentRunId: "r1" });
    rerender(
      <ChatThread
        workspaceId="ws1"
        messages={[{ id: "u", role: "user", run_id: "r1", text: "hi" }]}
        feature={null}
        starterPrompts={[]}
      />,
    );
    expect(
      screen.getByPlaceholderText(/或者直接说想法/),
    ).toBeInTheDocument();
  });
});
