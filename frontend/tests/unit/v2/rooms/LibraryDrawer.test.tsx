import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { LibraryDrawer } from "@/app/(workbench)/workspaces/[id]/components/rooms/LibraryDrawer";

const MOCK_ITEMS = [
  {
    id: "lib-1",
    title: "Attention Is All You Need",
    authors: ["Vaswani, A.", "Shazeer, N."],
    year: 2017,
    doi: "10.5555/3295222.3295349",
    url: undefined,
    abstract: undefined,
    source: "user_upload" as const,
    created_at: "2026-01-15T10:00:00Z",
  },
  {
    id: "lib-2",
    title: "BERT: Pre-training of Deep Bidirectional Transformers",
    authors: ["Devlin, J."],
    year: 2019,
    doi: undefined,
    url: "https://arxiv.org/abs/1810.04805",
    abstract: undefined,
    source: "search_result" as const,
    created_at: "2026-01-16T10:00:00Z",
  },
];

describe("LibraryDrawer", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders nothing when closed", () => {
    global.fetch = vi.fn();
    render(
      <LibraryDrawer
        workspaceId="ws-1"
        open={false}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("library-drawer")).not.toBeInTheDocument();
  });

  it("fetches and displays items when opened", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MOCK_ITEMS),
    });
    render(
      <LibraryDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Attention Is All You Need");
    expect(screen.getByText("Attention Is All You Need")).toBeInTheDocument();
    expect(screen.getByText(/BERT/)).toBeInTheDocument();
    expect(screen.getAllByTestId("library-item")).toHaveLength(2);
  });

  it("shows empty state when no items", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });
    render(
      <LibraryDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByTestId("drawer-empty");
    expect(screen.getByTestId("drawer-empty")).toHaveTextContent(
      "No library items found",
    );
  });

  it("shows error state on fetch failure", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({}),
    });
    render(
      <LibraryDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByTestId("drawer-error");
    expect(screen.getByTestId("drawer-error")).toHaveTextContent(
      "Failed to list library items",
    );
  });

  it("filters items by search query (title)", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MOCK_ITEMS),
    });
    render(
      <LibraryDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Attention Is All You Need");

    const searchInput = screen.getByTestId("drawer-search");
    fireEvent.change(searchInput, { target: { value: "attention" } });

    expect(screen.getByText("Attention Is All You Need")).toBeInTheDocument();
    expect(screen.queryByText(/BERT/)).not.toBeInTheDocument();
  });

  it("filters items by search query (author)", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MOCK_ITEMS),
    });
    render(
      <LibraryDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Attention Is All You Need");

    const searchInput = screen.getByTestId("drawer-search");
    fireEvent.change(searchInput, { target: { value: "Devlin" } });

    expect(screen.getByText(/BERT/)).toBeInTheDocument();
    expect(
      screen.queryByText("Attention Is All You Need"),
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
      <LibraryDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Attention Is All You Need");
    const deleteButtons = screen.getAllByTestId("item-delete");
    fireEvent.click(deleteButtons[0]);

    await waitFor(() => {
      expect(screen.getAllByTestId("library-item")).toHaveLength(1);
    });
  });

  it("applies initial query and highlights the focused library item", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MOCK_ITEMS),
    });
    render(
      <LibraryDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
        initialQuery="bert"
        focusItemId="lib-2"
      />,
    );

    await screen.findByText(/BERT/);
    expect(
      (screen.getByTestId("drawer-search") as HTMLInputElement).value,
    ).toBe("bert");
    expect(
      screen.queryByText("Attention Is All You Need"),
    ).not.toBeInTheDocument();
    const focusedItem = screen
      .getAllByTestId("library-item")
      .find((item) => item.getAttribute("data-item-id") === "lib-2");
    expect(focusedItem).toHaveAttribute("data-focused", "true");
  });

  it("calls onClose when close button clicked", async () => {
    const onClose = vi.fn();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });
    render(
      <LibraryDrawer
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
