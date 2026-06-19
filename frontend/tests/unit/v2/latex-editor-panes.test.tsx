import { createRef, forwardRef } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LatexEditorPanes } from "@/components/latex/latex-editor/LatexEditorPanes";

vi.mock("@/components/latex/LatexPdfPreview", () => ({
  LatexPdfPreview: ({
    className,
    currentPage,
    fitMode,
    zoomPercent,
  }: {
    className?: string;
    currentPage?: number;
    fitMode?: "width" | "page";
    zoomPercent?: number;
  }) => (
    <div
      className={className}
      data-current-page={currentPage}
      data-fit-mode={fitMode}
      data-testid="pdf-preview"
      data-zoom-percent={zoomPercent}
    />
  ),
}));

vi.mock("@/components/latex/latex-editor/PrismMonacoEditor", () => ({
  PrismMonacoEditor: forwardRef<HTMLDivElement, { value: string }>(
    function MockPrismMonacoEditor({ value }) {
      return <div data-testid="prism-editor">{value}</div>;
    },
  ),
}));

vi.mock("@/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  ResizablePanel: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  ResizableHandle: () => <div data-testid="resize-handle" />,
}));

const handlers = {
  onSurfaceModeChange: vi.fn(),
  onAssistOpenChange: vi.fn(),
  onOpenAssist: vi.fn(),
  onFileContentChange: vi.fn(),
  onSelectionChange: vi.fn(),
  onPdfSelection: vi.fn(),
  onCompile: vi.fn(),
  onOpenCompileLog: vi.fn(),
};

function renderPanes(surfaceMode: "edit" | "compare") {
  return render(
    <LatexEditorPanes
      surfaceMode={surfaceMode}
      activeFilePath="main.tex"
      activeFileKind="text"
      activeFileContent="\\begin{document}x\\end{document}"
      activeBlobUrl={null}
      dirty={false}
      isFileLoading={false}
      hasFeedbackSelection={false}
      selectionText=""
      pdfDraftSelection={null}
      editorRef={createRef()}
      compiledPdfUrl="/paper.pdf"
      pdfHighlightFeedbacks={[]}
      activeFeedbackId={null}
      transientPdfAnchor={null}
      isCompiling={false}
      isSaving={false}
      engine="xelatex"
      compileResult={null}
      {...handlers}
    />,
  );
}

describe("LatexEditorPanes", () => {
  it("shows the PDF open command only before the comparison surface is open", () => {
    const { rerender } = renderPanes("edit");

    expect(screen.getByRole("button", { name: "打开 PDF 对照" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "编辑" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "对照" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "审阅" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "专注" })).not.toBeInTheDocument();
    expect(screen.getByText("PDF 对照按需打开")).toBeInTheDocument();

    rerender(
      <LatexEditorPanes
        surfaceMode="compare"
        activeFilePath="main.tex"
        activeFileKind="text"
        activeFileContent="\\begin{document}x\\end{document}"
        activeBlobUrl={null}
        dirty={false}
        isFileLoading={false}
        hasFeedbackSelection={false}
        selectionText=""
        pdfDraftSelection={null}
        editorRef={createRef()}
        compiledPdfUrl="/paper.pdf"
        pdfHighlightFeedbacks={[]}
        activeFeedbackId={null}
        transientPdfAnchor={null}
        isCompiling={false}
        isSaving={false}
        engine="xelatex"
        compileResult={null}
        {...handlers}
      />,
    );

    expect(screen.queryByRole("button", { name: "打开 PDF 对照" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "收起 PDF" })).toBeInTheDocument();
  });

  it("renders an Overleaf-like PDF preview stage with compile, view, page, zoom, sync, and collapse controls", () => {
    renderPanes("compare");

    expect(screen.getByRole("toolbar", { name: "PDF 预览台" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新编译 PDF" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "同步滚动" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "适合宽度" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "整页" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByLabelText("PDF 页码")).toHaveValue(1);
    expect(screen.getByText("/ 1")).toBeInTheDocument();
    expect(screen.getByLabelText("PDF 缩放")).toHaveValue(100);
    expect(screen.getByRole("button", { name: "展开 PDF 预览" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "收起 PDF" })).toBeInTheDocument();
  });

  it("recompiles from the PDF preview stage toolbar", () => {
    handlers.onCompile.mockClear();
    renderPanes("compare");

    fireEvent.click(screen.getByRole("button", { name: "重新编译 PDF" }));

    expect(handlers.onCompile).toHaveBeenCalledTimes(1);
  });

  it("projects PDF stage controls into the preview renderer", () => {
    renderPanes("compare");

    const preview = screen.getByTestId("pdf-preview");
    expect(preview).toHaveAttribute("data-fit-mode", "width");
    expect(preview).toHaveAttribute("data-zoom-percent", "100");
    expect(preview).toHaveAttribute("data-current-page", "1");

    fireEvent.click(screen.getByRole("button", { name: "整页" }));
    expect(screen.getByTestId("pdf-preview")).toHaveAttribute("data-fit-mode", "page");

    fireEvent.change(screen.getByLabelText("PDF 缩放"), {
      target: { value: "130" },
    });
    expect(screen.getByTestId("pdf-preview")).toHaveAttribute("data-zoom-percent", "130");

    fireEvent.change(screen.getByLabelText("PDF 页码"), {
      target: { value: "2" },
    });
    expect(screen.getByTestId("pdf-preview")).toHaveAttribute("data-current-page", "2");
  });

  it("uses reversible PDF focus labels when expanding the preview stage", () => {
    renderPanes("compare");

    fireEvent.click(screen.getByRole("button", { name: "展开 PDF 预览" }));

    expect(screen.getByRole("button", { name: "收起 PDF 预览" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
