import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useLatexFeedbackWorkflow } from "@/components/latex/latex-editor/useLatexFeedbackWorkflow";

const mockLatexState = vi.hoisted(() => ({
  activeFileKind: "text" as const,
  activeFilePath: "main.tex",
  activeFileContent: "\\section{Intro}\nThis draft sounds automated.\n\\section{Method}\nMore text.",
  activeFileSavedContent: "\\section{Intro}\nThis draft sounds automated.\n\\section{Method}\nMore text.",
}));

const mockUseLatexStore = vi.hoisted(() =>
  Object.assign(vi.fn(), {
    getState: vi.fn(() => mockLatexState),
  }),
);

vi.mock("@/stores/latex", () => ({
  useLatexStore: mockUseLatexStore,
}));

vi.mock("@/lib/api", () => ({
  applyLatexFeedbackRewrite: vi.fn(),
  previewLatexFeedbackRewrite: vi.fn(),
  protectLatexSection: vi.fn(),
  revertLatexFeedbackRewrite: vi.fn(),
}));

function renderWorkflow(overrides: Partial<Parameters<typeof useLatexFeedbackWorkflow>[0]> = {}) {
  const sendChatMessage = vi.fn().mockResolvedValue({ executionId: "exec-1" });
  const setFeedbackStatus = vi.fn();
  const setFeedbackError = vi.fn();
  const prismOptimization = {
    addJob: vi.fn(),
    updateJob: vi.fn(),
  };
  const options: Parameters<typeof useLatexFeedbackWorkflow>[0] = {
    projectId: "latex-1",
    workspaceId: "ws-1",
    project: {
      id: "latex-1",
      name: "Prism Project",
      main_file: "main.tex",
      workspace_id: "ws-1",
    } as never,
    activeFilePath: "main.tex",
    activeFileKind: "text",
    activeFileContent: mockLatexState.activeFileContent,
    activeFileSavedContent: mockLatexState.activeFileSavedContent,
    compileHistoryId: null,
    selectionRange: [0, 0],
    pdfDraftSelection: null,
    transientPdfAnchor: null,
    feedbackItems: [],
    setFeedbackItems: vi.fn(),
    setFeedbackStatus,
    setFeedbackError,
    editorRef: { current: null },
    prismOptimization,
    sendChatMessage,
    isChatSending: false,
    openFile: vi.fn(),
    saveActiveFile: vi.fn(),
    setSelectedPath: vi.fn(),
    setSelectedPathType: vi.fn(),
    setSelectionRange: vi.fn(),
    setPdfDraftSelection: vi.fn(),
    setTransientPdfAnchor: vi.fn(),
    ...overrides,
  };

  return {
    ...renderHook(() => useLatexFeedbackWorkflow(options)),
    prismOptimization,
    sendChatMessage,
    setFeedbackStatus: options.setFeedbackStatus,
    setFeedbackError: options.setFeedbackError,
  };
}

describe("useLatexFeedbackWorkflow", () => {
  it("routes selected-text agent suggestions with lightweight local context", async () => {
    const selectedText = "This draft sounds automated.";
    const start = mockLatexState.activeFileContent.indexOf(selectedText);
    const { result, sendChatMessage } = renderWorkflow({
      selectionRange: [start, start + selectedText.length],
    });

    act(() => {
      result.current.actions.setFeedbackScope("selection");
      result.current.actions.setFeedbackDraftComment("把这一段写得更自然");
    });
    await act(async () => {
      await result.current.actions.addFeedbackAndRewrite();
    });

    const [, , , options] = sendChatMessage.mock.calls[0];
    const params = options.metadata.orchestration.params;

    expect(params.rewrite_mode).toBe("selection");
    expect(params.context_strategy).toBe("local_manuscript_rewrite");
    expect(params.context_requirements).toEqual({
      include_manuscript_context: true,
      include_workspace_history: false,
      include_related_documents: false,
      include_sandbox_artifacts: false,
      include_pending_review_summary: false,
    });
    expect(params.selected_text).toBe(selectedText);
    expect(params.instruction).toBe("把这一段写得更自然");
  });

  it("routes whole-document optimization as document scope", async () => {
    const { result, prismOptimization, sendChatMessage } = renderWorkflow();

    act(() => {
      result.current.actions.setFeedbackDraftComment("这篇文章 AI 味太浓了");
    });
    await act(async () => {
      await result.current.actions.launchDocumentOptimization();
    });

    expect(prismOptimization.addJob).toHaveBeenCalledWith(
      expect.objectContaining({
        filePath: "main.tex",
        scope: "document",
        instruction: "这篇文章 AI 味太浓了",
        selectedText: mockLatexState.activeFileContent,
      }),
    );
    const [, , , options] = sendChatMessage.mock.calls[0];
    const params = options.metadata.orchestration.params;

    expect(params.scope).toBe("document");
    expect(params.rewrite_mode).toBe("document");
    expect(params.context_strategy).toBe("workspace_manuscript_review");
    expect(params.context_requirements).toEqual({
      include_manuscript_context: true,
      include_workspace_history: true,
      include_related_documents: true,
      include_sandbox_artifacts: true,
      include_pending_review_summary: true,
    });
    expect(params.selected_text).toBe(mockLatexState.activeFileContent);
    expect(params.selection_start).toBe(0);
    expect(params.selection_end).toBe(mockLatexState.activeFileContent.length);
    expect(params.instruction).toBe("这篇文章 AI 味太浓了");
  });

  it("clears document optimization pending status when chat does not start a mission", async () => {
    const sendChatMessage = vi.fn().mockResolvedValue(undefined);
    const { result, setFeedbackStatus, setFeedbackError } = renderWorkflow({
      sendChatMessage,
    });

    act(() => {
      result.current.actions.setFeedbackDraftComment("这篇文章 AI 味太浓了");
    });
    await act(async () => {
      await result.current.actions.launchDocumentOptimization();
    });

    expect(setFeedbackError).toHaveBeenCalledWith(
      "未能启动全文修改；请在对话中补充修改目标后重试。",
    );
    expect(setFeedbackStatus).toHaveBeenLastCalledWith("");
  });
});
