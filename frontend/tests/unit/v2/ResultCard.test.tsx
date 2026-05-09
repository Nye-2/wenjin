import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { ResultCard } from "@/app/(workbench)/workspaces/[id]/v2/components/ResultCard";

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
  mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ committed: {} }) });
});

const SAMPLE_DATA = {
  execution_id: "exec-1",
  status: "completed" as const,
  duration_seconds: 23,
  narrative: "找到 15 篇相关文献",
  outputs: [
    { id: "o1", kind: "library_item" as const, preview: "Smith et al. 2024", default_checked: true, data: { title: "Deep Learning", authors: ["Smith"], year: 2024 } },
    { id: "o2", kind: "library_item" as const, preview: "Wang et al. 2023", default_checked: true, data: { title: "Transformers", authors: ["Wang"], year: 2023 } },
    { id: "o3", kind: "document" as const, preview: "综述初稿.docx", default_checked: false, data: { name: "综述初稿", mime_type: "docx", storage_path: "/tmp/d.docx", size_bytes: 1024, doc_kind: "draft" as const } },
  ],
};

describe("ResultCard", () => {
  it("renders outputs grouped by kind with default-checked", () => {
    render(<ResultCard data={SAMPLE_DATA} />);
    // Narrative should be visible
    expect(screen.getByText(/找到 15 篇相关文献/)).toBeInTheDocument();
    // 2 library items should be checked by default, 1 document unchecked
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes[0]).toBeChecked(); // o1 default_checked: true
    expect(checkboxes[1]).toBeChecked(); // o2 default_checked: true
    expect(checkboxes[2]).not.toBeChecked(); // o3 default_checked: false
  });

  it("calls commit with accept_all on '全部接受'", async () => {
    render(<ResultCard data={SAMPLE_DATA} />);
    fireEvent.click(screen.getByText("全部接受"));
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/executions/exec-1/commit",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Idempotency-Key": expect.any(String) }),
        body: JSON.stringify({ accept_all: true }),
      })
    );
  });

  it("calls commit with selected ids on '仅勾选项'", async () => {
    render(<ResultCard data={SAMPLE_DATA} />);
    fireEvent.click(screen.getByText("仅勾选项"));
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/executions/exec-1/commit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ accepted_ids: ["o1", "o2"] }), // only default-checked ones
      })
    );
  });

  it("calls commit with empty array on '全弃'", async () => {
    render(<ResultCard data={SAMPLE_DATA} />);
    fireEvent.click(screen.getByText("全弃"));
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/executions/exec-1/commit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ accepted_ids: [] }),
      })
    );
  });

  it("uses idempotency-key header", () => {
    render(<ResultCard data={SAMPLE_DATA} />);
    fireEvent.click(screen.getByText("全部接受"));
    const call = mockFetch.mock.calls[0][1];
    expect(call.headers["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("disables buttons after successful commit", async () => {
    render(<ResultCard data={SAMPLE_DATA} />);
    const acceptAllBtn = screen.getByText("全部接受");
    fireEvent.click(acceptAllBtn);

    // Wait for the commit to resolve and UI to update
    const confirmed = await screen.findByText("已保存");
    expect(confirmed).toBeInTheDocument();
    // Buttons are replaced by confirmation text — no longer in the DOM
    expect(screen.queryByText("全部接受")).not.toBeInTheDocument();
    expect(screen.queryByText("仅勾选项")).not.toBeInTheDocument();
    expect(screen.queryByText("全弃")).not.toBeInTheDocument();
    // Checkboxes are also disabled
    const checkboxes = screen.getAllByRole("checkbox");
    for (const cb of checkboxes) {
      expect(cb).toBeDisabled();
    }
  });

  it("allows toggling checkboxes before commit", () => {
    render(<ResultCard data={SAMPLE_DATA} />);
    const checkboxes = screen.getAllByRole("checkbox");

    // Toggle first checkbox off
    fireEvent.click(checkboxes[0]);
    expect(checkboxes[0]).not.toBeChecked();

    // Toggle third checkbox on
    fireEvent.click(checkboxes[2]);
    expect(checkboxes[2]).toBeChecked();
  });

  it("sends only manually checked ids after toggling", () => {
    render(<ResultCard data={SAMPLE_DATA} />);
    const checkboxes = screen.getAllByRole("checkbox");

    // Uncheck o1, check o3
    fireEvent.click(checkboxes[0]); // o1 off
    fireEvent.click(checkboxes[2]); // o3 on

    fireEvent.click(screen.getByText("仅勾选项"));
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/executions/exec-1/commit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ accepted_ids: ["o2", "o3"] }),
      })
    );
  });

  it("groups outputs by kind with section headers", () => {
    render(<ResultCard data={SAMPLE_DATA} />);
    expect(screen.getByText(/Library Items/)).toBeInTheDocument();
    expect(screen.getByText(/Documents/)).toBeInTheDocument();
  });

  it("shows duration when provided", () => {
    render(<ResultCard data={SAMPLE_DATA} />);
    expect(screen.getByText(/23s/)).toBeInTheDocument();
  });
});
