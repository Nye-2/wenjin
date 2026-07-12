import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { LatexEditorShell } from "@/components/latex/LatexEditorShell";

const mockCompileProject = vi.hoisted(() => vi.fn());
const mockLoadProject = vi.hoisted(() => vi.fn());
const mockLatexStoreOverrides = vi.hoisted(() => ({
  compileResult: null as unknown,
  fileChanges: [] as unknown[],
}));
const mockReviewQueueState = vi.hoisted(() => ({
  focusedReviewItemId: null as string | null,
  focusedLogicalKey: null as string | null,
}));
const mockWorkflowActions = vi.hoisted(() => ({
  setFeedbackDraftComment: vi.fn(),
  setFeedbackScope: vi.fn(),
  addFeedbackAndQuickRewrite: vi.fn(),
  addFeedbackAndRewrite: vi.fn(),
  launchDocumentOptimization: vi.fn(),
  addFeedbackOnly: vi.fn(),
  protectFile: vi.fn(),
  undoRewrite: vi.fn(),
  selectRewriteCandidate: vi.fn(),
  regenerateRewrite: vi.fn(),
  setDiffViewMode: vi.fn(),
  toggleWhitespaceOnlyDiff: vi.fn(),
  setAllDiffHunksCollapsed: vi.fn(),
  toggleDiffHunkCollapsed: vi.fn(),
  copySelectedRewrite: vi.fn(),
  cancelRewritePreview: vi.fn(),
  applyRewrite: vi.fn(),
  focusFeedback: vi.fn(),
  rewrite: vi.fn(),
  launchPrismOptimization: vi.fn(),
  removeFeedback: vi.fn(),
}));
const mockFeedbackWorkflowState = vi.hoisted(() => ({
  hasFeedbackSelection: false,
  selectionText: "",
  pdfHighlightFeedbacks: [],
  view: {
    feedbackContextText: "",
    feedbackDraftComment: "",
    feedbackScope: "selection" as const,
    canCreateFeedback: false,
    protectionStatus: "",
    protectionError: "",
    isProtectingActiveFile: false,
    lastRewriteUndo: null,
    isApplyingRewrite: false,
    selectedRewriteCandidate: null,
    selectedRewriteCandidateIndex: 0,
    rewriteCandidates: [],
    diffViewMode: "inline" as const,
    showWhitespaceOnlyDiff: false,
    collapsedDiffHunks: {},
    previewFeedbackItem: null,
    currentFileFeedbacks: [],
    activeFeedbackId: null,
    feedbackBusyId: null,
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/latex/latex-editor/LatexEditorProjectBar", () => ({
  LatexEditorProjectBar: ({ onCompile }: { onCompile: () => void }) => (
    <button type="button" data-testid="project-bar-compile" onClick={onCompile}>
      编译
    </button>
  ),
}));

vi.mock("@/components/latex/latex-editor/LatexEditorPanes", () => ({
  LatexEditorPanes: ({
    surfaceMode,
    stageLabel,
    onCompile,
    onOpenAssist,
  }: {
    surfaceMode: string;
    stageLabel?: string;
    onCompile: () => void;
    onOpenAssist: (intent: "selection" | "compile") => void;
  }) => (
    <section>
      <div data-testid="surface-mode">{surfaceMode}</div>
      <div data-testid="stage-label">{stageLabel}</div>
      <button type="button" onClick={onCompile}>
        面板编译
      </button>
      <button type="button" data-testid="open-compile-log" onClick={() => onOpenAssist("compile")}>
        查看编译日志
      </button>
    </section>
  ),
}));

vi.mock("@/components/latex/latex-editor/PrismOptimizationTraceDialog", () => ({
  PrismOptimizationTraceDialog: () => null,
}));

vi.mock("@/components/latex/latex-editor/LatexCompileLogDialog", () => ({
  LatexCompileLogDialog: () => null,
}));

vi.mock("@/components/latex/latex-editor/LatexResourceRail", () => ({
  LatexResourceRail: () => <aside data-testid="resource-rail" />,
}));

vi.mock("@/components/latex/latex-editor/usePrismOptimizationJobs", () => ({
  usePrismOptimizationJobs: () => ({
    activeJobId: null,
    activeJob: null,
    activeRecord: null,
    activePhases: [],
    jobs: [],
    optimizingFeedbackIds: new Set(),
    isTraceOpen: false,
    setTraceOpen: vi.fn(),
    setActiveJobId: vi.fn(),
  }),
}));

vi.mock("@/components/latex/latex-editor/usePrismReviewQueue", () => ({
  usePrismReviewQueue: () => ({
    fileChangesRef: { current: null },
    pendingReviewItems: [],
    appliedReviewItems: [],
    focusedReviewItemId: mockReviewQueueState.focusedReviewItemId,
    focusedLogicalKey: mockReviewQueueState.focusedLogicalKey,
    fileChangePreviews: {},
    busyFileChangeKey: null,
    fileChangeError: "",
    previewProjectFileChange: vi.fn(),
    discardPendingFileChange: vi.fn(),
    applyPendingFileChange: vi.fn(),
    revertAppliedFileChange: vi.fn(),
    scrollToReviewQueue: vi.fn(),
  }),
}));

vi.mock("@/components/latex/latex-editor/useLatexFeedbackPersistence", () => ({
  useLatexFeedbackPersistence: () => ({
    feedbackItems: [],
    feedbackLoaded: true,
    feedbackStatus: "",
    feedbackError: "",
    setFeedbackItems: vi.fn(),
    setFeedbackStatus: vi.fn(),
    setFeedbackError: vi.fn(),
  }),
}));

vi.mock("@/components/latex/latex-editor/useLatexPdfSelectionMapping", () => ({
  useLatexPdfSelectionMapping: () => ({
    pdfDraftSelection: null,
    transientPdfAnchor: null,
    setPdfDraftSelection: vi.fn(),
    setTransientPdfAnchor: vi.fn(),
    handlePdfSelection: vi.fn(),
  }),
}));

vi.mock("@/components/latex/latex-editor/useLatexFeedbackWorkflow", () => ({
  useLatexFeedbackWorkflow: () => ({
    ...mockFeedbackWorkflowState,
    actions: mockWorkflowActions,
  }),
}));

vi.mock("@/stores/auth", () => ({
  useAuthStore: () => ({ isAuthenticated: true, isLoading: false }),
}));

vi.mock("@/stores/chat-store", () => ({
  useChatStoreV2: (selector: (state: unknown) => unknown) =>
    selector({
      sendMessage: vi.fn(),
      isSending: false,
    }),
}));

vi.mock("@/stores/latex", () => ({
  useLatexStore: () => ({
    project: { id: "latex-1", name: "Prism Project", main_file: "main.tex" },
    tree: [],
    activeFilePath: "main.tex",
    activeFileKind: "text",
    activeFileContent: "\\begin{document}x\\end{document}",
    activeFileSavedContent: "\\begin{document}x\\end{document}",
    activeBlobUrl: null,
    fileChanges: mockLatexStoreOverrides.fileChanges as never[],
    appliedFileChanges: [],
    compileResult: mockLatexStoreOverrides.compileResult,
    compileLog: "",
    compiledPdfUrl: null,
    isProjectLoading: false,
    isFileLoading: false,
    isSaving: false,
    isCompiling: false,
    error: null,
    loadProject: mockLoadProject,
    setReviewState: vi.fn(),
    openFile: vi.fn(),
    setActiveFileContent: vi.fn(),
    saveActiveFile: vi.fn(),
    createFile: vi.fn(),
    createFolder: vi.fn(),
    renamePath: vi.fn(),
    deletePath: vi.fn(),
    saveOrder: vi.fn(),
    uploadFiles: vi.fn(),
    uploadDirectory: vi.fn(),
    uploadArchive: vi.fn(),
    applyFileChange: vi.fn(),
    discardFileChange: vi.fn(),
    revertFileChange: vi.fn(),
    deleteProject: vi.fn(),
    compileProject: mockCompileProject,
  }),
}));

describe("Prism editor shell", () => {
  beforeEach(() => {
    Object.values(mockWorkflowActions).forEach((action) => action.mockReset());
    mockFeedbackWorkflowState.hasFeedbackSelection = false;
    mockFeedbackWorkflowState.selectionText = "";
    mockFeedbackWorkflowState.pdfHighlightFeedbacks = [];
    mockFeedbackWorkflowState.view.feedbackContextText = "";
    mockFeedbackWorkflowState.view.feedbackDraftComment = "";
    mockFeedbackWorkflowState.view.canCreateFeedback = false;
    mockFeedbackWorkflowState.view.currentFileFeedbacks = [];
    mockFeedbackWorkflowState.view.selectedRewriteCandidate = null;
    mockFeedbackWorkflowState.view.previewFeedbackItem = null;
    mockFeedbackWorkflowState.view.feedbackBusyId = null;
    mockLatexStoreOverrides.compileResult = null;
    mockLatexStoreOverrides.fileChanges = [];
    mockReviewQueueState.focusedReviewItemId = null;
    mockReviewQueueState.focusedLogicalKey = null;
    mockCompileProject.mockReset();
    mockCompileProject.mockResolvedValue(undefined);
    mockLoadProject.mockReset();
    mockLoadProject.mockResolvedValue(undefined);
  });

  it("opens the PDF comparison surface immediately when compiling", async () => {
    render(<LatexEditorShell projectId="latex-1" workspaceId="ws-1" />);

    expect(screen.getByTestId("surface-mode")).toHaveTextContent("edit");
    fireEvent.click(screen.getByTestId("project-bar-compile"));

    expect(mockCompileProject).toHaveBeenCalledWith("xelatex");
    expect(screen.getByTestId("surface-mode")).toHaveTextContent("compare");
    expect(screen.getByTestId("stage-label")).toHaveTextContent("PDF 预览台");
    expect(screen.queryByRole("dialog", { name: "改稿助手" })).not.toBeInTheDocument();
  });

  it("does not open AI assist automatically when compile result fails", async () => {
    mockLatexStoreOverrides.compileResult = {
      ok: false,
      status: 1,
      engine: "xelatex",
      main_file: "main.tex",
      error: "Undefined control sequence",
      history_id: "compile-1",
    };

    render(<LatexEditorShell projectId="latex-1" workspaceId="ws-1" />);

    expect(screen.queryByRole("dialog", { name: "改稿助手" })).not.toBeInTheDocument();
  });

  it("opens compile diagnostics without opening the AI assist panel", async () => {
    render(<LatexEditorShell projectId="latex-1" workspaceId="ws-1" />);

    fireEvent.click(screen.getByTestId("open-compile-log"));

    expect(screen.queryByRole("dialog", { name: "改稿助手" })).not.toBeInTheDocument();
  });

  it("uses floating AI assist instead of a fixed side rail by default", async () => {
    render(<LatexEditorShell projectId="latex-1" workspaceId="ws-1" />);

    expect(screen.getByRole("button", { name: "改稿助手" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "改稿助手" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "关闭 改稿助手" })).not.toBeInTheDocument();
  });

  it("keeps pending review changes behind the floating entry unless a review link is focused", async () => {
    mockLatexStoreOverrides.fileChanges = [{ id: "change-1", file_path: "main.tex" }];

    render(<LatexEditorShell projectId="latex-1" workspaceId="ws-1" />);

    expect(screen.getByRole("button", { name: "改稿助手，待应用修改" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "改稿助手" })).not.toBeInTheDocument();
  });

  it("opens the assist panel when the route focuses a review item", async () => {
    mockReviewQueueState.focusedReviewItemId = "review-1";

    render(<LatexEditorShell projectId="latex-1" workspaceId="ws-1" />);

    expect(screen.getByRole("dialog", { name: "改稿助手" })).toBeInTheDocument();
  });

  it("opens the assist panel from selection shortcuts without launching work immediately", async () => {
    mockFeedbackWorkflowState.hasFeedbackSelection = true;
    mockFeedbackWorkflowState.selectionText = "selected manuscript text";
    mockFeedbackWorkflowState.view.feedbackContextText = "当前 TeX 已选中 24 个字符。";
    mockFeedbackWorkflowState.view.feedbackDraftComment = "";
    mockFeedbackWorkflowState.view.canCreateFeedback = false;

    const { unmount } = render(<LatexEditorShell projectId="latex-1" workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "改这段" }));

    expect(screen.getByRole("dialog", { name: "改稿助手" })).toBeInTheDocument();
    expect(mockWorkflowActions.addFeedbackAndQuickRewrite).not.toHaveBeenCalled();
    expect(mockWorkflowActions.addFeedbackAndRewrite).not.toHaveBeenCalled();
    expect(mockWorkflowActions.launchDocumentOptimization).not.toHaveBeenCalled();

    unmount();
    render(<LatexEditorShell projectId="latex-1" workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "修改全文" }));

    expect(screen.getByRole("dialog", { name: "改稿助手" })).toBeInTheDocument();
    expect(mockWorkflowActions.addFeedbackAndQuickRewrite).not.toHaveBeenCalled();
    expect(mockWorkflowActions.addFeedbackAndRewrite).not.toHaveBeenCalled();
    expect(mockWorkflowActions.launchDocumentOptimization).not.toHaveBeenCalled();
  });

  it("shows selection actions and routes local/document assist separately", async () => {
    mockFeedbackWorkflowState.hasFeedbackSelection = true;
    mockFeedbackWorkflowState.selectionText = "selected manuscript text";
    mockFeedbackWorkflowState.view.feedbackContextText = "当前 TeX 已选中 24 个字符。";
    mockFeedbackWorkflowState.view.feedbackDraftComment = "增强贡献表达";
    mockFeedbackWorkflowState.view.canCreateFeedback = true;

    render(<LatexEditorShell projectId="latex-1" workspaceId="ws-1" />);

    expect(screen.getByRole("dialog", { name: "改稿助手" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "改稿助手" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "改这段" }));
    fireEvent.click(screen.getByRole("button", { name: "修改全文" }));

    expect(mockWorkflowActions.addFeedbackAndQuickRewrite).toHaveBeenCalled();
    expect(mockWorkflowActions.addFeedbackAndRewrite).not.toHaveBeenCalled();
    expect(mockWorkflowActions.launchDocumentOptimization).toHaveBeenCalled();
  });

  it("routes no-selection whole-document assist to the async document workflow", async () => {
    mockFeedbackWorkflowState.view.feedbackContextText = "直接说你想怎么改，问津会通读当前主稿并生成可确认的修改建议。";
    mockFeedbackWorkflowState.view.feedbackDraftComment = "这篇文章 AI 味太浓了";
    mockFeedbackWorkflowState.view.canCreateFeedback = false;

    render(<LatexEditorShell projectId="latex-1" workspaceId="ws-1" />);

    expect(screen.getByRole("dialog", { name: "改稿助手" })).toBeInTheDocument();
    expect(screen.getByText("直接说你想怎么改，问津会通读当前主稿并生成可确认的修改建议。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "改这段" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "修改全文" }));

    expect(mockWorkflowActions.addFeedbackAndRewrite).not.toHaveBeenCalled();
    expect(mockWorkflowActions.launchDocumentOptimization).toHaveBeenCalled();
  });
});
