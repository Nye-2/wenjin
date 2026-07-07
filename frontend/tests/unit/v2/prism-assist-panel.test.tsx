import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PrismAssistPanel } from "@/components/latex/latex-editor/PrismAssistPanel";
import { fileChangeToPrismReviewItem } from "@/components/prism/PrismReviewList";

vi.mock("@/components/latex/latex-editor/LatexRewritePreviewPanel", () => ({
  LatexRewritePreviewPanel: () => <div data-testid="rewrite-preview">改写 diff 预览</div>,
}));

function renderPanel(overrides: Partial<React.ComponentProps<typeof PrismAssistPanel>> = {}) {
  const props: React.ComponentProps<typeof PrismAssistPanel> = {
    open: true,
    contextText: "当前 TeX 已选中 12 个字符。",
    draftComment: "",
    scope: "selection",
    canCreate: true,
    canUseDocumentAssist: true,
    canDeepAssist: true,
    hasSelectionContext: true,
    busy: false,
    isSaving: false,
    status: "",
    error: "",
    annotations: [
      {
        id: "fb-1",
        file_path: "main.tex",
        start: 0,
        end: 12,
        selected_text: "hello world",
        comment: "更学术一点",
        created_at: "2026-06-05T00:00:00Z",
        source: "tex",
        last_status: "idle",
        last_error: "",
      },
    ],
    activeFeedbackId: null,
    selectedRewriteCandidate: null,
    selectedRewriteCandidateIndex: -1,
    rewriteCandidates: [],
    diffViewMode: "inline",
    showWhitespaceOnlyDiff: false,
    collapsedDiffHunks: {},
    previewFeedbackItem: null,
    feedbackBusyId: null,
    isApplyingRewrite: false,
    runningJobCount: 0,
    protectionStatus: "",
    protectionError: "",
    isProtectingActiveFile: false,
    canProtectActiveFile: true,
    fileChangesRef: { current: null },
    fileChanges: [],
    appliedFileChanges: [],
    pendingReviewItems: [],
    appliedReviewItems: [],
    focusedReviewItemId: null,
    focusedLogicalKey: null,
    fileChangePreviews: {},
    busyFileChangeKey: null,
    fileChangeError: "",
    onClose: vi.fn(),
    onDraftChange: vi.fn(),
    onScopeChange: vi.fn(),
    onSaveComment: vi.fn(),
    onQuickRewrite: vi.fn(),
    onDeepAssist: vi.fn(),
    onFocusAnnotation: vi.fn(),
    onQuickRewriteAnnotation: vi.fn(),
    onDeepAssistAnnotation: vi.fn(),
    onRemoveAnnotation: vi.fn(),
    onSelectCandidate: vi.fn(),
    onRegenerate: vi.fn(),
    onDiffViewModeChange: vi.fn(),
    onToggleWhitespaceOnlyDiff: vi.fn(),
    onCollapseAllDiffHunks: vi.fn(),
    onToggleDiffHunkCollapsed: vi.fn(),
    onCopyRewrite: vi.fn(),
    onCancelRewrite: vi.fn(),
    onApplyRewrite: vi.fn(),
    onProtectActiveFile: vi.fn(),
    onPreviewProjectFileChange: vi.fn(),
    onDiscardPendingFileChange: vi.fn(),
    onApplyPendingFileChange: vi.fn(),
    onRevertAppliedFileChange: vi.fn(),
    ...overrides,
  };
  render(<PrismAssistPanel {...props} />);
  return props;
}

describe("PrismAssistPanel", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders nothing while closed", () => {
    renderPanel({ open: false });

    expect(screen.queryByRole("dialog", { name: "改稿助手" })).not.toBeInTheDocument();
  });

  it("renders composer and primary assist actions", () => {
    const props = renderPanel({ annotations: [] });

    fireEvent.change(screen.getByPlaceholderText("例如：这段太像模板文风了，请整体改得更像研究者写作。"), {
      target: { value: "增强贡献表达" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加批注" }));
    fireEvent.click(screen.getByRole("button", { name: "改这段" }));
    fireEvent.click(screen.getByRole("button", { name: "修改全文" }));

    expect(screen.getByRole("dialog", { name: "改稿助手" })).toBeInTheDocument();
    expect(props.onDraftChange).toHaveBeenCalledWith("增强贡献表达");
    expect(props.onSaveComment).toHaveBeenCalled();
    expect(props.onQuickRewrite).toHaveBeenCalled();
    expect(props.onDeepAssist).toHaveBeenCalled();
  });

  it("keeps idle panel compact instead of showing empty heavy sections", () => {
    renderPanel({
      contextText: "直接说你想怎么改，问津会通读当前主稿并生成可确认的修改建议。",
      canCreate: false,
      canUseDocumentAssist: true,
      canDeepAssist: false,
      hasSelectionContext: false,
      annotations: [],
      canProtectActiveFile: true,
    });

    const dialog = screen.getByRole("dialog", { name: "改稿助手" });

    expect(dialog).toHaveAttribute("data-position", "bottom-right");
    expect(screen.getByPlaceholderText("例如：这段太像模板文风了，请整体改得更像研究者写作。")).toBeInTheDocument();
    expect(screen.getByText("直接说你想怎么改，问津会通读当前主稿并生成可确认的修改建议。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "修改全文" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "改这段" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重置改稿助手面板位置" })).toBeInTheDocument();
    expect(screen.queryByText("文件安全")).not.toBeInTheDocument();
    expect(screen.queryByText("待复核写入")).not.toBeInTheDocument();
    expect(screen.queryByText("当前文件批注")).not.toBeInTheDocument();
  });

  it("routes a one-sentence whole-document instruction to document rewrite", () => {
    const props = renderPanel({
      contextText: "直接说你想怎么改，问津会通读当前主稿并生成可确认的修改建议。",
      canCreate: false,
      canUseDocumentAssist: true,
      canDeepAssist: true,
      hasSelectionContext: false,
      annotations: [],
    });

    fireEvent.change(screen.getByPlaceholderText("例如：这段太像模板文风了，请整体改得更像研究者写作。"), {
      target: { value: "这篇文章 AI 味太浓了" },
    });
    fireEvent.click(screen.getByRole("button", { name: "修改全文" }));

    expect(props.onDraftChange).toHaveBeenCalledWith("这篇文章 AI 味太浓了");
    expect(props.onDeepAssist).toHaveBeenCalled();
    expect(screen.queryByText("固定侧栏")).not.toBeInTheDocument();
  });

  it("renders current file annotations with quick and deep actions", () => {
    const props = renderPanel();

    const annotationSection = screen.getByText("当前文件批注").closest("section");
    if (!annotationSection) {
      throw new Error("Annotation section should render");
    }
    const annotationControls = within(annotationSection);

    fireEvent.click(annotationControls.getByRole("button", { name: "定位" }));
    fireEvent.click(annotationControls.getByRole("button", { name: "改这段" }));
    fireEvent.click(annotationControls.getByRole("button", { name: "生成建议" }));
    fireEvent.click(annotationControls.getByRole("button", { name: "删除" }));

    expect(screen.getByText("更学术一点")).toBeInTheDocument();
    expect(props.onFocusAnnotation).toHaveBeenCalledWith(props.annotations[0]);
    expect(props.onQuickRewriteAnnotation).toHaveBeenCalledWith(props.annotations[0]);
    expect(props.onDeepAssistAnnotation).toHaveBeenCalledWith(props.annotations[0]);
    expect(props.onRemoveAnnotation).toHaveBeenCalledWith("fb-1");
  });

  it("renders rewrite preview when candidates exist", () => {
    renderPanel({
      selectedRewriteCandidate: {
        candidate_id: "c-1",
        candidate_signature: "sig",
        model_id: "model",
        scope: "selection",
        profile: "balanced",
        risk_level: "low",
        section_title: "",
        section_level: "",
        target_start: 0,
        target_end: 5,
        rewritten_text: "hello",
        proposed_content: "hello",
        changes_summary: "改进表达",
        updated_anchor: {
          selected_text: "hello",
          prefix: "",
          suffix: "",
          heading_title: "",
          heading_level: "",
          line_hint: 1,
        },
        base_file_hash: "hash",
        base_range_hash: "range",
        diff: {
          stats: {
            tokens_changed: 1,
            chars_added: 1,
            chars_deleted: 0,
            citation_changed: 0,
            label_changed: 0,
            math_changed: 0,
          },
          risk_flags: [],
          hunks: [],
        },
      },
      rewriteCandidates: [],
    });

    expect(screen.getByTestId("rewrite-preview")).toBeInTheDocument();
  });

  it("keeps review queue and file protection inside the assist panel", () => {
    const pendingChange = {
      id: "fc-1",
      logical_key: "section:intro",
      path: "main.tex",
      reason: "Generated workspace manuscript",
      status: "pending",
      title: "main.tex",
    };
    const appliedChange = {
      id: "fc-2",
      logical_key: "section:method",
      path: "main.tex",
      reason: "可撤回的写入记录",
      status: "applied",
      title: "已写入稿件修改: main.tex",
      previous_hash: "prev",
      applied_hash: "applied",
      revert_signature: "sig",
    };
    const props = renderPanel({
      protectionStatus: "当前文件已保护",
      fileChanges: [pendingChange],
      appliedFileChanges: [appliedChange],
      pendingReviewItems: [fileChangeToPrismReviewItem(pendingChange)],
      appliedReviewItems: [fileChangeToPrismReviewItem(appliedChange)],
    });

    fireEvent.click(screen.getByRole("button", { name: "保护当前文件" }));
    fireEvent.click(screen.getByRole("button", { name: "预览 diff" }));
    fireEvent.click(screen.getByRole("button", { name: "忽略" }));
    fireEvent.click(screen.getByRole("button", { name: /^应用$/ }));
    fireEvent.click(screen.getByRole("button", { name: "撤回" }));

    expect(screen.getByText("待复核写入")).toBeInTheDocument();
    expect(screen.getByText("已写入变更")).toBeInTheDocument();
    expect(screen.getByText("当前文件已保护")).toBeInTheDocument();
    expect(props.onProtectActiveFile).toHaveBeenCalled();
    expect(props.onPreviewProjectFileChange).toHaveBeenCalledWith(pendingChange);
    expect(props.onDiscardPendingFileChange).toHaveBeenCalledWith(pendingChange);
    expect(props.onApplyPendingFileChange).toHaveBeenCalledWith(pendingChange);
    expect(props.onRevertAppliedFileChange).toHaveBeenCalledWith(appliedChange);
  });
});
