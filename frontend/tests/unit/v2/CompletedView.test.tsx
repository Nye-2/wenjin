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
});
