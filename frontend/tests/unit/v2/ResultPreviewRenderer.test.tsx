import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResultPreviewRenderer } from "@/app/(workbench)/workspaces/[id]/components/result-preview/ResultPreviewRenderer";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";

describe("ResultPreviewRenderer", () => {
  it("renders image previews as a safe figure placeholder with the workspace path", () => {
    const preview = {
      id: "fig-1",
      source: "staged_output",
      kind: "figure",
      title: "Accuracy trend",
      subtitle: "Validation accuracy improved across epochs.",
      badge: "图表",
      previewMode: "image",
      previewText: "Validation accuracy improved across epochs.",
      previewPath: "/workspace/outputs/figures/run-1/figure.png",
      metadataLines: ["strategy: matplotlib_line_chart"],
      defaultChecked: true,
      canCommit: true,
      canOpenRoom: true,
    } as unknown as WorkspaceResultPreview;

    render(<ResultPreviewRenderer preview={preview} />);

    expect(screen.getByTestId("result-preview-image")).toBeInTheDocument();
    expect(screen.getByText("图表预览")).toBeInTheDocument();
    expect(
      screen.getByText("/workspace/outputs/figures/run-1/figure.png"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
