import { createRef, forwardRef } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LatexEditorPanes } from "@/components/latex/latex-editor/LatexEditorPanes";

vi.mock("@/components/latex/LatexPdfPreview", () => ({
  LatexPdfPreview: () => <div data-testid="pdf-preview" />,
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
});
