import { describe, expect, it } from "vitest";

import { extractTaskOutputs } from "@/lib/workbench-result-outputs";

describe("workbench-result-outputs", () => {
  it("extracts user-visible staged outputs", () => {
    const outputs = extractTaskOutputs({
      task_report: {
        outputs: [
          {
            id: "doc-1",
            kind: "document",
            preview: "Outline",
            default_checked: true,
            data: { name: "outline.md", content: "# Old" },
          },
          {
            id: "mem-1",
            kind: "memory_fact",
            preview: "Hidden workspace context",
            default_checked: true,
            data: { content: "Hidden workspace context" },
          },
        ],
      },
    });

    expect(outputs).toEqual([
      {
        id: "doc-1",
        kind: "document",
        preview: "Outline",
        default_checked: true,
        data: { name: "outline.md", content: "# Old" },
      },
    ]);
  });

  it("does not default-select outputs from partial executions", () => {
    const outputs = extractTaskOutputs({
      task_report: {
        status: "failed_partial",
        outputs: [
          {
            id: "doc-1",
            kind: "document",
            preview: "Draft",
            default_checked: true,
            data: { name: "draft.md", content: "# Draft" },
          },
        ],
      },
    });

    expect(outputs[0].default_checked).toBe(false);
  });
});
