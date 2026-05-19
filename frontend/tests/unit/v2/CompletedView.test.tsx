import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CompletedView } from "@/app/(workbench)/workspaces/[id]/components/CompletedView";

describe("CompletedView", () => {
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
    expect(screen.getByText("Smith et al. 2024")).toBeInTheDocument();
    expect(screen.getByText("429")).toBeInTheDocument();
  });

  it("renders nested task_report payloads from fetched execution records", () => {
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
                data: { name: "outline.md" },
              },
            ],
            errors: [],
          },
        }}
      />,
    );

    expect(screen.getByText("Outline completed.")).toBeInTheDocument();
    expect(screen.getByText("Thesis outline")).toBeInTheDocument();

    fireEvent.click(screen.getByText("View full result"));
    expect(screen.getByText(/"task_report"/)).toBeInTheDocument();
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
});
