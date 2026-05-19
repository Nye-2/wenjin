import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { DocumentsDrawer } from "@/app/(workbench)/workspaces/[id]/components/rooms/DocumentsDrawer";

const MOCK_ITEMS = [
  {
    id: "doc-1",
    name: "Research Paper Draft",
    mime_type: "application/pdf",
    doc_kind: "draft" as const,
    size_bytes: 1024000,
    created_at: "2026-01-15T10:00:00Z",
    updated_at: "2026-01-16T12:00:00Z",
  },
  {
    id: "doc-2",
    name: "Literature Review Outline",
    mime_type: "text/markdown",
    doc_kind: "outline" as const,
    size_bytes: 20480,
    created_at: "2026-01-14T08:00:00Z",
    updated_at: "2026-01-14T09:00:00Z",
  },
];

describe("DocumentsDrawer", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders nothing when closed", () => {
    global.fetch = vi.fn();
    render(
      <DocumentsDrawer
        workspaceId="ws-1"
        open={false}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("documents-drawer")).not.toBeInTheDocument();
  });

  it("fetches and displays items when opened", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MOCK_ITEMS),
    });
    render(
      <DocumentsDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Research Paper Draft");
    expect(screen.getByText("Research Paper Draft")).toBeInTheDocument();
    expect(screen.getByText("Literature Review Outline")).toBeInTheDocument();
    expect(screen.getAllByTestId("document-item")).toHaveLength(2);
    // Check kind badges
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("Outline")).toBeInTheDocument();
  });

  it("shows empty state when no items", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });
    render(
      <DocumentsDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByTestId("drawer-empty");
    expect(screen.getByTestId("drawer-empty")).toHaveTextContent(
      "No documents found",
    );
  });

  it("shows error state on fetch failure", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({}),
    });
    render(
      <DocumentsDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByTestId("drawer-error");
    expect(screen.getByTestId("drawer-error")).toHaveTextContent(
      "Failed to list documents",
    );
  });

  it("filters items by search query", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MOCK_ITEMS),
    });
    render(
      <DocumentsDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Research Paper Draft");

    const searchInput = screen.getByTestId("drawer-search");
    fireEvent.change(searchInput, { target: { value: "draft" } });

    expect(screen.getByText("Research Paper Draft")).toBeInTheDocument();
    expect(
      screen.queryByText("Literature Review Outline"),
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
      <DocumentsDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Research Paper Draft");
    const deleteButtons = screen.getAllByTestId("item-delete");
    fireEvent.click(deleteButtons[0]);

    await waitFor(() => {
      expect(screen.getAllByTestId("document-item")).toHaveLength(1);
    });
  });

  it("applies initial query and highlights the focused document", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MOCK_ITEMS),
    });
    render(
      <DocumentsDrawer
        workspaceId="ws-1"
        open={true}
        onClose={vi.fn()}
        initialQuery="outline"
        focusItemId="doc-2"
      />,
    );

    await screen.findByText("Literature Review Outline");
    expect(
      (screen.getByTestId("drawer-search") as HTMLInputElement).value,
    ).toBe("outline");
    expect(
      screen.queryByText("Research Paper Draft"),
    ).not.toBeInTheDocument();
    const focusedItem = screen
      .getAllByTestId("document-item")
      .find((item) => item.getAttribute("data-item-id") === "doc-2");
    expect(focusedItem).toHaveAttribute("data-focused", "true");
  });

  it("calls onClose when close button clicked", async () => {
    const onClose = vi.fn();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });
    render(
      <DocumentsDrawer
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
