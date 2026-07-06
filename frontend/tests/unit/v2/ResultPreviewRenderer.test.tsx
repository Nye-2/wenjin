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

  it("renders real image previews when a safe preview url is available", () => {
    const preview = {
      id: "fig-1",
      source: "staged_output",
      kind: "figure",
      title: "Accuracy trend",
      subtitle: "Validation accuracy improved across epochs.",
      badge: "图表",
      previewMode: "image",
      previewText: "Validation accuracy improved across epochs.",
      previewUrl: "/api/workspaces/ws-1/files/outputs/figures/run-1/figure.png",
      metadataLines: [],
      defaultChecked: true,
      canCommit: true,
      canOpenRoom: true,
    } as unknown as WorkspaceResultPreview;

    render(<ResultPreviewRenderer preview={preview} />);

    const image = screen.getByRole("img", { name: "Accuracy trend 图像预览" });
    expect(image).toHaveAttribute(
      "src",
      "/api/workspaces/ws-1/files/outputs/figures/run-1/figure.png",
    );
    expect(screen.getByText("已加载图像预览。")).toBeInTheDocument();
  });

  it("explains unavailable previews in Chinese with the next action", () => {
    const preview = {
      id: "doc-1",
      source: "staged_output",
      kind: "document",
      title: "开题报告",
      subtitle: null,
      badge: "文档",
      previewMode: "plain_text",
      previewText: null,
      metadataLines: [],
      defaultChecked: false,
      canCommit: true,
      canOpenRoom: true,
    } as unknown as WorkspaceResultPreview;

    render(<ResultPreviewRenderer preview={preview} />);

    expect(screen.getByText("暂时无法预览这项结果")).toBeInTheDocument();
    expect(
      screen.getByText("请先在复核区确认是否保存；保存后可在对应工作区房间继续查看。"),
    ).toBeInTheDocument();
  });

  it("renders document excerpts with a clear heading", () => {
    const preview = {
      id: "doc-1",
      source: "staged_output",
      kind: "document",
      title: "开题报告",
      subtitle: null,
      badge: "文档",
      previewMode: "markdown",
      previewText: "## 研究背景\n这里是摘要。",
      metadataLines: [],
      defaultChecked: false,
      canCommit: true,
      canOpenRoom: true,
    } as unknown as WorkspaceResultPreview;

    render(<ResultPreviewRenderer preview={preview} />);

    expect(screen.getByTestId("result-preview-document-excerpt")).toBeInTheDocument();
    expect(screen.getByText("文档摘录")).toBeInTheDocument();
    expect(screen.getByText("研究背景")).toBeInTheDocument();
  });

  it("renders document diff previews", () => {
    const preview = {
      id: "doc-diff-1",
      source: "staged_output",
      kind: "document",
      title: "方法段落修改",
      subtitle: null,
      badge: "文档",
      previewMode: "document_diff",
      previewText: "修改前\n旧段落\n\n修改后\n新段落",
      metadataLines: [],
      defaultChecked: false,
      canCommit: true,
      canOpenRoom: true,
    } as unknown as WorkspaceResultPreview;

    render(<ResultPreviewRenderer preview={preview} />);

    expect(screen.getByTestId("result-preview-document-diff")).toBeInTheDocument();
    expect(screen.getByText("文档修改对比")).toBeInTheDocument();
    expect(screen.getByText(/旧段落/)).toBeInTheDocument();
    expect(screen.getByText(/新段落/)).toBeInTheDocument();
  });
});
