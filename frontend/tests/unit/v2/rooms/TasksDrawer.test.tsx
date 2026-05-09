import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { TasksDrawer } from "@/app/(workbench)/workspaces/[id]/v2/components/rooms/TasksDrawer";

const MOCK_ITEMS = [
  {
    id: "task-1",
    title: "Write introduction section",
    description: "Draft the intro",
    status: "in_progress" as const,
    priority: 1,
    created_at: "2026-01-15T10:00:00Z",
  },
  {
    id: "task-2",
    title: "Review methodology",
    description: undefined,
    status: "pending" as const,
    priority: 2,
    created_at: "2026-01-16T10:00:00Z",
  },
];

describe("TasksDrawer", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders nothing when closed", () => {
    global.fetch = vi.fn();
    render(
      <TasksDrawer
        workspaceId="ws-1"
        open={false}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("tasks-drawer")).not.toBeInTheDocument();
  });

  it("fetches and displays items when opened", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MOCK_ITEMS),
    });
    render(
      <TasksDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Write introduction section");
    expect(screen.getByText("Write introduction section")).toBeInTheDocument();
    expect(screen.getByText("Review methodology")).toBeInTheDocument();
    expect(screen.getAllByTestId("task-item")).toHaveLength(2);
  });

  it("shows empty state when no items", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });
    render(
      <TasksDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByTestId("drawer-empty");
    expect(screen.getByTestId("drawer-empty")).toHaveTextContent(
      "No tasks found",
    );
  });

  it("shows error state on fetch failure", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({}),
    });
    render(
      <TasksDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByTestId("drawer-error");
    expect(screen.getByTestId("drawer-error")).toHaveTextContent(
      "Failed to list tasks",
    );
  });

  it("filters items by search query", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MOCK_ITEMS),
    });
    render(
      <TasksDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Write introduction section");

    const searchInput = screen.getByTestId("drawer-search");
    fireEvent.change(searchInput, { target: { value: "review" } });

    expect(screen.getByText("Review methodology")).toBeInTheDocument();
    expect(
      screen.queryByText("Write introduction section"),
    ).not.toBeInTheDocument();
  });

  it("deletes an item", async () => {
    global.fetch = vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
      if (opts?.method === "DELETE") {
        return Promise.resolve({ ok: true });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(MOCK_ITEMS),
      });
    });

    render(
      <TasksDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Write introduction section");
    const deleteButtons = screen.getAllByTestId("item-delete");
    fireEvent.click(deleteButtons[0]);

    await waitFor(() => {
      expect(screen.getAllByTestId("task-item")).toHaveLength(1);
    });
  });

  it("creates a new task via add form", async () => {
    const newTask = {
      id: "task-new",
      title: "New task",
      description: undefined,
      status: "pending" as const,
      priority: undefined,
      created_at: "2026-01-17T10:00:00Z",
    };

    global.fetch = vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
      if (opts?.method === "POST") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(newTask),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(MOCK_ITEMS),
      });
    });

    render(
      <TasksDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Write introduction section");

    // Open add form
    fireEvent.click(screen.getByTestId("add-task-btn"));
    expect(screen.getByTestId("add-task-form")).toBeInTheDocument();

    // Type and submit
    const input = screen.getByTestId("add-task-input");
    fireEvent.change(input, { target: { value: "New task" } });
    fireEvent.click(screen.getByTestId("add-task-submit"));

    await waitFor(() => {
      expect(screen.getByText("New task")).toBeInTheDocument();
    });
  });

  it("toggles task status", async () => {
    global.fetch = vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
      if (opts?.method === "PATCH") {
        return Promise.resolve({ ok: true });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(MOCK_ITEMS),
      });
    });

    render(
      <TasksDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Write introduction section");

    // Toggle first task (in_progress -> completed)
    const toggles = screen.getAllByTestId("task-status-toggle");
    fireEvent.click(toggles[0]);

    await waitFor(() => {
      expect(toggles[0]).toHaveTextContent("completed");
    });
  });

  it("calls onClose when close button clicked", async () => {
    const onClose = vi.fn();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });
    render(
      <TasksDrawer
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
