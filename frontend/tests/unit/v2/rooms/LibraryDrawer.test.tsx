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

  it("renders normalized source payload items returned by the library API", async () => {
    const sourcePayload = {
      id: "src-1",
      workspace_id: "ws-1",
      title: "OpenFedLLM: Training Large Language Models on Decentralized Private Data",
      authors_json: ["Tianshi Che", "Ji Liu"],
      year: 2023,
      abstract: "A Semantic Scholar search result.",
      ingest_label: "execution:run-1",
      source_kind: "paper",
      library_status: "included",
      created_at: "2026-05-23T00:00:00Z",
    };
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/library/src-1")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(sourcePayload),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ items: [sourcePayload], count: 1 }),
      });
    });
    render(
      <LibraryDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText(/OpenFedLLM/);
    expect(screen.getByText("Tianshi Che, Ji Liu")).toBeInTheDocument();
    expect(screen.getByText("研究团队")).toBeInTheDocument();
    expect(
      await screen.findByText("A Semantic Scholar search result."),
    ).toBeInTheDocument();
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
      "资料库暂无文献",
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
      "文献资料加载失败",
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

  it("shows the selected library item in a detail pane", async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/library/lib-2")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              id: "lib-2",
              title: "BERT: Pre-training of Deep Bidirectional Transformers",
              authors: ["Devlin, J."],
              year: 2019,
              url: "https://arxiv.org/abs/1810.04805",
              abstract: "A foundational pre-training paper.",
              source: "search_result",
              created_at: "2026-01-16T10:00:00Z",
            }),
        });
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
        focusItemId="lib-2"
      />,
    );

    await screen.findByText("A foundational pre-training paper.");
    expect(
      screen.getAllByText(
        "BERT: Pre-training of Deep Bidirectional Transformers",
      ),
    ).toHaveLength(2);
  });

  it("updates the focused library item when the room seed changes while open", async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/library/lib-1")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              id: "lib-1",
              title: "Attention Is All You Need",
              authors: ["Vaswani, A.", "Shazeer, N."],
              year: 2017,
              abstract: "The transformer paper.",
              source: "user_upload",
              created_at: "2026-01-15T10:00:00Z",
            }),
        });
      }
      if (url.includes("/library/lib-2")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              id: "lib-2",
              title: "BERT: Pre-training of Deep Bidirectional Transformers",
              authors: ["Devlin, J."],
              year: 2019,
              abstract: "A foundational pre-training paper.",
              source: "search_result",
              created_at: "2026-01-16T10:00:00Z",
            }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(MOCK_ITEMS),
      });
    });

    const { rerender } = render(
      <LibraryDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
        focusItemId="lib-1"
      />,
    );

    await screen.findByText("The transformer paper.");

    rerender(
      <LibraryDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
        focusItemId="lib-2"
      />,
    );

    await screen.findByText("A foundational pre-training paper.");
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
