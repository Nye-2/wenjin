import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompletedView } from "@/app/(workbench)/workspaces/[id]/components/CompletedView";

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("CompletedView", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          committed: { documents: 1, library: 0 },
          room_targets: {
            documents: [{ output_id: "doc-1", item_id: "saved-doc-1" }],
            library: [],
          },
        }),
    });
  });

  it("renders TaskReport payloads from execution.completed", () => {
    render(
      <CompletedView
        result={{
          execution_id: "exec-1",
          capability_id: "lit_review",
          status: "failed_partial",
          duration_seconds: 8,
          narrative: "Found useful papers, with one source unavailable.",
          outputs: [
            {
              id: "paper-1",
              kind: "library_item",
              preview: "Smith et al. 2024",
              default_checked: true,
              data: { title: "Deep Learning", authors: ["Smith"] },
            },
          ],
          errors: [{ phase: "search", task: "semantic_scholar", error: "429" }],
        }}
      />,
    );

    expect(
      screen.getByText("Found useful papers, with one source unavailable."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Smith et al. 2024")).toHaveLength(2);
    expect(screen.getByText("429")).toBeInTheDocument();
  });

  it("renders nested task_report payloads as preview-first detail", () => {
    render(
      <CompletedView
        result={{
          task_report: {
            execution_id: "exec-1",
            capability_id: "outline",
            status: "completed",
            duration_seconds: 5,
            narrative: "Outline completed.",
            outputs: [
              {
                id: "doc-1",
                kind: "document",
                preview: "Thesis outline",
                default_checked: true,
                data: {
                  name: "outline.md",
                  mime_type: "text/markdown",
                  doc_kind: "outline",
                  content: "# Chapter 1\n- Background",
                },
              },
            ],
            errors: [],
          },
        }}
      />,
    );

    expect(screen.getByText("Outline completed.")).toBeInTheDocument();
    expect(screen.getAllByText("Thesis outline")).toHaveLength(2);
    expect(screen.getByText("Chapter 1")).toBeInTheDocument();
    expect(screen.getByText("Background")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "View full result" }),
    ).not.toBeInTheDocument();
  });

  it("builds resume links for supported execution next actions", () => {
    render(
      <CompletedView
        workspaceId="ws-1"
        featureId="framework_outline"
        executionId="exec-42"
        nextActions={[
          {
            action: "resume_execution",
            label: "继续执行",
          },
        ]}
      />,
    );

    const link = screen.getByRole("link", { name: "继续执行" });
    const url = new URL(link.getAttribute("href")!, "https://example.test");
    expect(url.pathname).toBe("/workspaces/ws-1");
    expect(url.searchParams.get("feature")).toBe("framework_outline");
    expect(url.searchParams.get("entry")).toBe("resume");
    expect(url.searchParams.get("execution_id")).toBe("exec-42");
  });

  it("keeps supported non-link actions visible as explicit badges", () => {
    render(
      <CompletedView
        nextActions={[
          {
            action: "continue_thread",
          },
        ]}
      />,
    );

    expect(screen.getByText("继续在对话中处理")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "继续在对话中处理" }),
    ).not.toBeInTheDocument();
  });

  it("routes open artifact actions into workspace rooms when no explicit url exists", () => {
    render(
      <CompletedView
        workspaceId="ws-1"
        nextActions={[
          {
            action: "open_artifact",
            artifact_kind: "document",
            artifact_id: "doc-7",
            item_id: "doc-1",
            title: "Research Paper Draft",
          },
        ]}
      />,
    );

    const link = screen.getByRole("link", { name: "查看产物" });
    const url = new URL(link.getAttribute("href")!, "https://example.test");
    expect(url.pathname).toBe("/workspaces/ws-1");
    expect(url.searchParams.get("room")).toBe("documents");
    expect(url.searchParams.get("artifact_id")).toBe("doc-7");
    expect(url.searchParams.get("item_id")).toBe("doc-1");
    expect(url.searchParams.get("query")).toBe("Research Paper Draft");
  });

  it("routes Prism preview actions to the workspace Prism file-change focus", () => {
    render(
      <CompletedView
        workspaceId="ws-1"
        result={{
          data: {
            latex_project_id: "latex-1",
            file_changes: [
              {
                logical_key: "section:introduction",
                path: "sections/introduction.tex",
              },
            ],
          },
        }}
        nextActions={[
          {
            action: "preview_prism_changes",
            label: "预览待确认修改",
          },
        ]}
      />,
    );

    const link = screen.getByRole("link", { name: "预览待确认修改" });
    expect(link).toHaveAttribute(
      "href",
      "/workspaces/ws-1/prism?focus=file_changes",
    );
    expect(screen.getByText("sections/introduction.tex")).toBeInTheDocument();
  });

  it("commits staged previews from the execution panel and exposes saved room links", async () => {
    render(
      <CompletedView
        workspaceId="ws-1"
        executionId="exec-1"
        result={{
          task_report: {
            execution_id: "exec-1",
            capability_id: "outline",
            status: "completed",
            narrative: "Outline completed.",
            outputs: [
              {
                id: "doc-1",
                kind: "document",
                preview: "Thesis outline",
                default_checked: true,
                data: {
                  name: "outline.md",
                  mime_type: "text/markdown",
                  doc_kind: "outline",
                  content: "# Chapter 1\n- Background",
                },
              },
            ],
          },
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "保存到工作区" }));

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/executions/exec-1/commit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ accept_all: true }),
      }),
    );

    const savedLink = await screen.findByRole("link", { name: "打开已保存的 Thesis outline" });
    const url = new URL(savedLink.getAttribute("href")!, "https://example.test");
    expect(url.pathname).toBe("/workspaces/ws-1");
    expect(url.searchParams.get("room")).toBe("documents");
    expect(url.searchParams.get("item_id")).toBe("saved-doc-1");
    expect(url.searchParams.get("query")).toBe("Thesis outline");
  });

  it("shows a save error inline when execution commit fails", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ detail: "Commit failed" }),
    });

    render(
      <CompletedView
        workspaceId="ws-1"
        executionId="exec-1"
        result={{
          task_report: {
            execution_id: "exec-1",
            capability_id: "outline",
            status: "completed",
            narrative: "Outline completed.",
            outputs: [
              {
                id: "doc-1",
                kind: "document",
                preview: "Thesis outline",
                default_checked: true,
                data: {
                  name: "outline.md",
                  mime_type: "text/markdown",
                  doc_kind: "outline",
                  content: "# Chapter 1\n- Background",
                },
              },
            ],
          },
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "保存到工作区" }));
    expect(await screen.findByText("Commit failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存到工作区" })).toBeInTheDocument();
  });
});
