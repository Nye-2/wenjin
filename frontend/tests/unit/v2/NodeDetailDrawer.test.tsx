import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { NodeDetailDrawer } from "@/app/(workbench)/workspaces/[id]/components/NodeDetailDrawer";

const NODE_DETAIL = {
  id: "node-1",
  label: "Search",
  status: "completed",
  phase_index: 0,
  input: { query: "machine learning" },
  output: { results_count: 15 },
  thinking: "Searching for relevant papers...",
  tools: [
    {
      name: "scholar_search",
      args: { query: "machine learning" },
      result: "15 papers found",
    },
  ],
  token_usage: { input: 150, output: 200 },
  started_at: "2026-01-01T00:00:00Z",
  completed_at: "2026-01-01T00:01:00Z",
};

describe("NodeDetailDrawer", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders loading state", () => {
    global.fetch = vi.fn().mockReturnValue(new Promise(() => {}));
    render(
      <NodeDetailDrawer
        executionId="exec-1"
        nodeId="node-1"
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByTestId("drawer-loading")).toBeInTheDocument();
  });

  it("fetches and displays node detail", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(NODE_DETAIL),
    });
    render(
      <NodeDetailDrawer
        executionId="exec-1"
        nodeId="node-1"
        onClose={vi.fn()}
      />,
    );
    await screen.findByText("Search");
    expect(screen.getByText("Search")).toBeInTheDocument();
    expect(screen.getByText(/completed/)).toBeInTheDocument();
  });

  it("shows error state when fetch fails", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({}),
    });
    render(
      <NodeDetailDrawer
        executionId="exec-1"
        nodeId="node-1"
        onClose={vi.fn()}
      />,
    );
    await screen.findByTestId("drawer-error");
    expect(screen.getByTestId("drawer-error")).toBeInTheDocument();
  });

  it("switches tabs", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(NODE_DETAIL),
    });
    render(
      <NodeDetailDrawer
        executionId="exec-1"
        nodeId="node-1"
        onClose={vi.fn()}
      />,
    );
    await screen.findByText("Search");

    // Default tab is Input
    expect(screen.getByTestId("tab-content-input")).toBeInTheDocument();

    // Switch to Thinking tab
    fireEvent.click(screen.getByText("Thinking"));
    expect(screen.getByTestId("tab-content-thinking")).toBeInTheDocument();
    expect(
      screen.getByText("Searching for relevant papers..."),
    ).toBeInTheDocument();

    // Switch to Tools tab
    fireEvent.click(screen.getByText("Tools"));
    expect(screen.getByTestId("tab-content-tools")).toBeInTheDocument();
    expect(screen.getByText("scholar_search")).toBeInTheDocument();

    // Switch to Output tab
    fireEvent.click(screen.getByText("Output"));
    expect(screen.getByTestId("tab-content-output")).toBeInTheDocument();
    expect(screen.getByText(/results_count/)).toBeInTheDocument();
  });

  it("calls onClose when close button clicked", async () => {
    const onClose = vi.fn();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(NODE_DETAIL),
    });
    render(
      <NodeDetailDrawer
        executionId="exec-1"
        nodeId="node-1"
        onClose={onClose}
      />,
    );
    await screen.findByText("Search");
    fireEvent.click(screen.getByTestId("drawer-close"));
    // onClose is called after 200ms animation
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("displays token usage footer", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(NODE_DETAIL),
    });
    render(
      <NodeDetailDrawer
        executionId="exec-1"
        nodeId="node-1"
        onClose={vi.fn()}
      />,
    );
    await screen.findByText("Search");
    expect(screen.getByText(/In: 150/)).toBeInTheDocument();
    expect(screen.getByText(/Out: 200/)).toBeInTheDocument();
  });
});
