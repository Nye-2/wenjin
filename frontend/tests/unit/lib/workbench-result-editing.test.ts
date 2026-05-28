import { describe, expect, it } from "vitest";

import {
  applyDraftEditsToOutputs,
  buildOutputOverrides,
  extractTaskOutputs,
} from "@/lib/workbench-result-editing";

describe("workbench-result-editing", () => {
  it("extracts staged outputs and overlays draft edits", () => {
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
        ],
      },
    });

    const edited = applyDraftEditsToOutputs(outputs, {
      "doc-1": { data: { name: "edited.md" }, preview: "Edited outline" },
    });

    expect(edited[0].preview).toBe("Edited outline");
    expect(edited[0].data?.name).toBe("edited.md");
    expect(edited[0].data?.content).toBe("# Old");
  });

  it("builds commit overrides only for accepted edited outputs", () => {
    const overrides = buildOutputOverrides(["doc-1"], {
      "doc-1": { data: { content: "# Updated" } },
      "doc-2": { data: { content: "# Ignored" } },
    });

    expect(overrides).toEqual({
      "doc-1": { data: { content: "# Updated" } },
    });
  });
});
