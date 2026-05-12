import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { RunsDrawer } from "@/app/(workbench)/workspaces/[id]/components/rooms/RunsDrawer";

const MOCK_ITEMS = [
  {
    id: "run-1",
    capability_name: "Literature Search",
    status: "completed" as const,
    started_at: "2026-01-15T10:00:00Z",
    completed_at: "2026-01-15T10:02:30Z",
    summary: "Found 25 relevant papers",
    token_usage: { input: 500, output: 1200 },
  },
  {
    id: "run-2",
    capability_name: "Deep Research",
    status: "failed" as const,
    started_at: "2026-01-16T08:00:00Z",
    completed_at: "2026-01-16T08:01:00Z",
    summary: "Error: rate limit exceeded",
    token_usage: undefined,
  },
  {
    id: "run-3",
    capability_name: "Paper Writing",
    status: "running" as const,
    started_at: "2026-01-17T09:00:00Z",
    completed_at: undefined,
    summary: "Generating draft...",
    token_usage: { input: 800, output: 2000 },
  },
];

describe("RunsDrawer", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders nothing when closed", () => {
    global.fetch = vi.fn();
    render(
      <RunsDrawer
        workspaceId="ws-1"
        open={false}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("runs-drawer")).not.toBeInTheDocument();
  });

  it("fetches and displays items when opened", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MOCK_ITEMS),
    });
    render(
      <RunsDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Literature Search");
    expect(screen.getByText("Literature Search")).toBeInTheDocument();
    expect(screen.getByText("Deep Research")).toBeInTheDocument();
    expect(screen.getByText("Paper Writing")).toBeInTheDocument();
    expect(screen.getAllByTestId("run-item")).toHaveLength(3);
  });

  it("shows status badges for each run", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MOCK_ITEMS),
    });
    render(
      <RunsDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Literature Search");
    const statuses = screen.getAllByTestId("run-status");
    expect(statuses[0]).toHaveTextContent("completed");
    expect(statuses[1]).toHaveTextContent("failed");
    expect(statuses[2]).toHaveTextContent("running");
  });

  it("shows empty state when no items", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });
    render(
      <RunsDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByTestId("drawer-empty");
    expect(screen.getByTestId("drawer-empty")).toHaveTextContent(
      "No runs found",
    );
  });

  it("shows error state on fetch failure", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({}),
    });
    render(
      <RunsDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByTestId("drawer-error");
    expect(screen.getByTestId("drawer-error")).toHaveTextContent(
      "Failed to list runs",
    );
  });

  it("filters items by search query", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MOCK_ITEMS),
    });
    render(
      <RunsDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Literature Search");

    const searchInput = screen.getByTestId("drawer-search");
    fireEvent.change(searchInput, { target: { value: "deep" } });

    expect(screen.getByText("Deep Research")).toBeInTheDocument();
    expect(screen.queryByText("Literature Search")).not.toBeInTheDocument();
  });

  it("calls onClose when close button clicked", async () => {
    const onClose = vi.fn();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });
    render(
      <RunsDrawer
        workspaceId="ws-1"
        open={true}
        onClose={onClose}
      />,
    );

    await screen.findByTestId("drawer-close");
    fireEvent.click(screen.getByTestId("drawer-close"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
