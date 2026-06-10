import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import type {
  Dispatch,
  RefObject,
  SetStateAction,
} from "react";

import type {
  LatexFeedbackItem,
  LatexFeedbackRewriteCandidate,
  LatexPdfAnchor,
  LatexProject,
} from "@/lib/api";
import {
  applyLatexFeedbackRewrite,
  previewLatexFeedbackRewrite,
  protectLatexSection,
  revertLatexFeedbackRewrite,
} from "@/lib/api";
import type { SendMessageResult } from "@/stores/chat-store";
import { useLatexStore } from "@/stores/latex";
import {
  buildFeedbackAnchor,
  parsePdfAnchor,
  resolveFeedbackRange,
  shiftFeedbacksAfterRewrite,
} from "./feedbackAnchors";
import {
  createPrismOptimizationJobId,
  type PrismOptimizationJob,
} from "./prismOptimizationJobs";
import type { PrismTextEditorHandle } from "./PrismMonacoEditor";
import {
  STALE_REWRITE_ERROR_CODES,
  STRUCTURE_REWRITE_ERROR_CODES,
} from "./rewriteDisplay";
import type {
  LastRewriteUndoState,
  PdfDraftSelection,
} from "./types";
import {
  readClientErrorCode,
  readClientErrorDetailField,
  readClientErrorMessage,
} from "./clientErrors";
import { useLatexFeedbackCreation } from "./useLatexFeedbackCreation";

type ActiveFileKind = "text" | "blob" | null;

const LOCAL_REWRITE_CONTEXT_REQUIREMENTS = {
  include_manuscript_context: true,
  include_workspace_history: false,
  include_related_documents: false,
  include_sandbox_artifacts: false,
  include_pending_review_summary: true,
};

const DOCUMENT_REWRITE_CONTEXT_REQUIREMENTS = {
  include_manuscript_context: true,
  include_workspace_history: true,
  include_related_documents: true,
  include_sandbox_artifacts: true,
  include_pending_review_summary: true,
};

interface FeedbackPrismOptimizationBridge {
  addJob(job: PrismOptimizationJob): void;
  updateJob(
    jobId: string,
    updater: (job: PrismOptimizationJob) => PrismOptimizationJob,
  ): void;
}

interface UseLatexFeedbackWorkflowOptions {
  projectId: string;
  workspaceId?: string;
  project: LatexProject | null;
  activeFilePath: string | null;
  activeFileKind: ActiveFileKind;
  activeFileContent: string;
  activeFileSavedContent: string;
  compileHistoryId?: string | null;
  selectionRange: [number, number];
  pdfDraftSelection: PdfDraftSelection | null;
  transientPdfAnchor: LatexPdfAnchor | null;
  feedbackItems: LatexFeedbackItem[];
  setFeedbackItems: Dispatch<SetStateAction<LatexFeedbackItem[]>>;
  setFeedbackStatus: (message: string) => void;
  setFeedbackError: (message: string) => void;
  editorRef: RefObject<PrismTextEditorHandle | null>;
  prismOptimization: FeedbackPrismOptimizationBridge;
  sendChatMessage: (
    workspaceId: string,
    content: string,
    attachments?: Array<{ name: string; path: string }>,
    options?: {
      skill?: string | null;
      metadata?: Record<string, unknown> | null;
    },
  ) => Promise<SendMessageResult | void>;
  isChatSending: boolean;
  openFile: (path: string) => Promise<void>;
  saveActiveFile: () => Promise<void>;
  setSelectedPath: (path: string) => void;
  setSelectedPathType: (type: "file" | "dir") => void;
  setSelectionRange: (range: [number, number]) => void;
  setPdfDraftSelection: (selection: PdfDraftSelection | null) => void;
  setTransientPdfAnchor: (anchor: LatexPdfAnchor | null) => void;
  onReviewStateChanged?: () => void;
}

export function useLatexFeedbackWorkflow({
  projectId,
  workspaceId,
  project,
  activeFilePath,
  activeFileKind,
  activeFileContent,
  activeFileSavedContent,
  compileHistoryId,
  selectionRange,
  pdfDraftSelection,
  transientPdfAnchor,
  feedbackItems,
  setFeedbackItems,
  setFeedbackStatus,
  setFeedbackError,
  editorRef,
  prismOptimization,
  sendChatMessage,
  isChatSending,
  openFile,
  saveActiveFile,
  setSelectedPath,
  setSelectedPathType,
  setSelectionRange,
  setPdfDraftSelection,
  setTransientPdfAnchor,
  onReviewStateChanged,
}: UseLatexFeedbackWorkflowOptions) {
  const [feedbackDraftComment, setFeedbackDraftComment] = useState("");
  const [feedbackScope, setFeedbackScope] = useState<"selection" | "section">("section");
  const [activeFeedbackId, setActiveFeedbackId] = useState<string | null>(null);
  const [feedbackBusyId, setFeedbackBusyId] = useState<string | null>(null);
  const [rewritePreviewFilePath, setRewritePreviewFilePath] = useState<string | null>(null);
  const [rewritePreviewFeedbackId, setRewritePreviewFeedbackId] = useState<string | null>(null);
  const [rewriteCandidates, setRewriteCandidates] = useState<LatexFeedbackRewriteCandidate[]>([]);
  const [selectedRewriteCandidateId, setSelectedRewriteCandidateId] = useState<string | null>(null);
  const [diffViewMode, setDiffViewMode] = useState<"inline" | "side-by-side">("inline");
  const [showWhitespaceOnlyDiff, setShowWhitespaceOnlyDiff] = useState(false);
  const [collapsedDiffHunks, setCollapsedDiffHunks] = useState<Record<string, boolean>>({});
  const [isApplyingRewrite, setIsApplyingRewrite] = useState(false);
  const [lastRewriteUndo, setLastRewriteUndo] = useState<LastRewriteUndoState | null>(null);
  const [isProtectingActiveFile, setIsProtectingActiveFile] = useState(false);
  const [protectionStatus, setProtectionStatus] = useState("");
  const [protectionError, setProtectionError] = useState("");

  const selectionText = useMemo(() => {
    if (activeFileKind !== "text") {
      return "";
    }
    const [start, end] = selectionRange;
    if (end <= start) {
      return "";
    }
    return activeFileContent.slice(start, end);
  }, [activeFileContent, activeFileKind, selectionRange]);

  const hasPdfDraftSelection = Boolean(pdfDraftSelection?.text.trim());
  const hasFeedbackSelection = selectionText.trim().length > 0 || hasPdfDraftSelection;
  const canCreateFeedback = Boolean(
    feedbackDraftComment.trim()
    && hasFeedbackSelection,
  );
  const feedbackContextText = selectionText.trim()
    ? `当前 TeX 已选中 ${selectionText.length} 个字符。`
    : hasPdfDraftSelection
      ? `当前 PDF 已选中 ${pdfDraftSelection?.text.trim().length || 0} 个字符。`
      : "直接说你想怎么改，问津会通读当前主稿并生成可确认的修改建议。";
  const currentFileFeedbacks = useMemo(
    () =>
      feedbackItems.filter(
        (item) => item.file_path === activeFilePath,
      ),
    [activeFilePath, feedbackItems],
  );
  const pdfHighlightFeedbacks = useMemo(
    () =>
      feedbackItems.map((item) => ({
        id: item.id,
        selectedText: item.selected_text,
        pdfAnchor: parsePdfAnchor(item.pdf_anchor),
      })),
    [feedbackItems],
  );
  const selectedRewriteCandidate = useMemo(() => {
    if (!rewriteCandidates.length) {
      return null;
    }
    if (!selectedRewriteCandidateId) {
      return rewriteCandidates[0];
    }
    return rewriteCandidates.find((item) => item.candidate_id === selectedRewriteCandidateId) || rewriteCandidates[0];
  }, [rewriteCandidates, selectedRewriteCandidateId]);
  const selectedRewriteCandidateIndex = useMemo(() => {
    if (!selectedRewriteCandidate) {
      return -1;
    }
    return rewriteCandidates.findIndex(
      (item) => item.candidate_id === selectedRewriteCandidate.candidate_id,
    );
  }, [rewriteCandidates, selectedRewriteCandidate]);
  const previewFeedbackItem = useMemo(
    () => feedbackItems.find((item) => item.id === rewritePreviewFeedbackId) || null,
    [feedbackItems, rewritePreviewFeedbackId],
  );

  const createFeedbackFromSelection = useLatexFeedbackCreation({
    projectId,
    activeFilePath,
    activeFileKind,
    activeFileContent,
    compileHistoryId,
    feedbackDraftComment,
    pdfDraftSelection,
    transientPdfAnchor,
    selectionRange,
    editorRef,
    openFile,
    setSelectedPath,
    setSelectedPathType,
    setSelectionRange,
    setTransientPdfAnchor,
    setFeedbackStatus,
    setFeedbackError,
  });

  const clearRewritePreview = useCallback((resetPending = true) => {
    const previewFeedbackId = rewritePreviewFeedbackId;
    if (resetPending && previewFeedbackId) {
      setFeedbackItems((prev) =>
        prev.map((entry) => (
          entry.id === previewFeedbackId && entry.last_status === "pending"
            ? {
              ...entry,
              last_status: "idle",
              last_error: "",
            }
            : entry
        )),
      );
    }
    setRewritePreviewFilePath(null);
    setRewritePreviewFeedbackId(null);
    setRewriteCandidates([]);
    setSelectedRewriteCandidateId(null);
    setDiffViewMode("inline");
    setCollapsedDiffHunks({});
  }, [rewritePreviewFeedbackId, setFeedbackItems]);

  useEffect(() => {
    setCollapsedDiffHunks({});
  }, [selectedRewriteCandidateId, rewritePreviewFeedbackId]);

  useEffect(() => {
    setSelectionRange([0, 0]);
    setFeedbackDraftComment("");
    setActiveFeedbackId(null);
    setFeedbackBusyId(null);
    clearRewritePreview();
  }, [activeFilePath, clearRewritePreview, setSelectionRange]);

  const addFeedbackOnly = useCallback(async () => {
    const item = await createFeedbackFromSelection(false);
    if (!item) {
      return;
    }
    setFeedbackError("");
    setFeedbackStatus("点评已保存。");
    setFeedbackItems((prev) => [...prev, item]);
    setActiveFeedbackId(item.id);
    setFeedbackDraftComment("");
    setPdfDraftSelection(null);
  }, [
    createFeedbackFromSelection,
    setFeedbackError,
    setFeedbackItems,
    setFeedbackStatus,
    setPdfDraftSelection,
  ]);

  const focusFeedback = useCallback((item: LatexFeedbackItem) => {
    if (!editorRef.current || activeFileKind !== "text") {
      return;
    }
    const resolved = resolveFeedbackRange(item, activeFileContent);
    if (!resolved) {
      setActiveFeedbackId(item.id);
      setFeedbackError("无法在当前文本中定位该点评。");
      return;
    }
    editorRef.current.focus();
    editorRef.current.setSelectionRange(resolved.start, resolved.end);
    setSelectionRange([resolved.start, resolved.end]);
    setTransientPdfAnchor(null);
    setActiveFeedbackId(item.id);
    setFeedbackError("");
  }, [activeFileContent, activeFileKind, editorRef, setFeedbackError, setSelectionRange, setTransientPdfAnchor]);

  const removeFeedback = useCallback((feedbackId: string) => {
    setFeedbackItems((prev) => prev.filter((item) => item.id !== feedbackId));
    if (activeFeedbackId === feedbackId) {
      setActiveFeedbackId(null);
    }
    if (rewritePreviewFeedbackId === feedbackId) {
      clearRewritePreview(false);
    }
    if (lastRewriteUndo?.feedback_id === feedbackId) {
      setLastRewriteUndo(null);
    }
  }, [
    activeFeedbackId,
    clearRewritePreview,
    lastRewriteUndo,
    rewritePreviewFeedbackId,
    setFeedbackItems,
  ]);

  const launchPrismOptimizationFromFeedback = useCallback(async (item: LatexFeedbackItem) => {
    const effectiveWorkspaceId = workspaceId || project?.workspace_id || "";
    if (!effectiveWorkspaceId) {
      setFeedbackError("当前 Prism 项目尚未关联 workspace，无法启动智能优化。");
      return;
    }
    if (!project) {
      setFeedbackError("项目尚未加载完成。");
      return;
    }
    if (isChatSending) {
      setFeedbackError("左侧对话正在处理消息，请稍后再生成这段修改。");
      return;
    }

    setFeedbackBusyId(item.id);
    setFeedbackError("");
    setFeedbackStatus("正在生成这段的修改建议。");
    try {
      if (activeFilePath !== item.file_path) {
        setSelectedPath(item.file_path);
        setSelectedPathType("file");
        await openFile(item.file_path);
      }

      let latexState = useLatexStore.getState();
      if (latexState.activeFileKind !== "text" || !latexState.activeFilePath) {
        throw new Error("当前文件不可生成这段修改。");
      }
      if (latexState.activeFileContent !== latexState.activeFileSavedContent) {
        await saveActiveFile();
        latexState = useLatexStore.getState();
      }

      const launchContent = latexState.activeFileContent;
      const resolved = resolveFeedbackRange(item, launchContent);
      if (!resolved) {
        throw new Error("无法在当前文本中定位该点评原文。");
      }
      const anchor = item.anchor || buildFeedbackAnchor(launchContent, resolved.start, resolved.end);
      const jobId = createPrismOptimizationJobId();
      const job: PrismOptimizationJob = {
        id: jobId,
        feedbackId: item.id,
        status: "launching",
        filePath: item.file_path,
        scope: feedbackScope,
        instruction: item.comment,
        selectedText: resolved.text,
        createdAt: new Date().toISOString(),
      };
      prismOptimization.addJob(job);
      setFeedbackItems((prev) =>
        prev.map((entry) =>
          entry.id === item.id
            ? { ...entry, last_status: "pending", last_error: "" }
            : entry,
        ),
      );

      const prompt = [
        "请启动「Prism 局部改稿」能力（prism_selection_optimize）。",
        `目标文件：${item.file_path}`,
        `改稿范围：${feedbackScope === "section" ? "所在 section" : "仅选区"}`,
        "用户指令：",
        item.comment,
        "请生成 Prism 待确认写入，不要直接覆盖正文。",
      ].join("\n");
      const result = await sendChatMessage(effectiveWorkspaceId, prompt, [], {
        metadata: {
          prism_selection_optimize: {
            job_id: jobId,
            feedback_id: item.id,
            latex_project_id: project.id,
            file_path: item.file_path,
          },
          orchestration: {
            params: {
              goal: "Prism 局部改稿",
              source_surface: "prism",
              rewrite_mode: feedbackScope === "section" ? "section" : "selection",
              context_strategy: "local_manuscript_rewrite",
              context_requirements: LOCAL_REWRITE_CONTEXT_REQUIREMENTS,
              latex_project_id: project.id,
              main_file: project.main_file,
              file_path: item.file_path,
              file_content: launchContent,
              selected_text: resolved.text,
              instruction: item.comment,
              comment: item.comment,
              selection_start: resolved.start,
              selection_end: resolved.end,
              anchor,
              pdf_anchor: item.pdf_anchor || null,
              scope: feedbackScope,
              feedback_id: item.id,
            },
          },
        },
      });

      if (result?.executionId) {
        prismOptimization.updateJob(
          jobId,
          (entry) => ({ ...entry, executionId: result.executionId ?? undefined, status: "running" }),
        );
        setFeedbackStatus("这段修改已启动，右下角可查看生成过程。");
        return;
      }

      const detail =
        typeof result?.toolResult?.detail === "string" && result.toolResult.detail.trim()
          ? result.toolResult.detail.trim()
          : "未能生成这段修改，请稍后重试。";
      prismOptimization.updateJob(
        jobId,
        (entry) => ({
          ...entry,
          status: result?.status === "advisory" ? "advisory" : "failed",
          error: detail,
        }),
      );
      setFeedbackItems((prev) =>
        prev.map((entry) =>
          entry.id === item.id
            ? { ...entry, last_status: "error", last_error: detail }
            : entry,
        ),
      );
      setFeedbackError(detail);
    } catch (err) {
      const message = readClientErrorMessage(err);
      setFeedbackItems((prev) =>
        prev.map((entry) =>
          entry.id === item.id
            ? { ...entry, last_status: "error", last_error: message }
            : entry,
        ),
      );
      setFeedbackError(`生成修改失败: ${message}`);
    } finally {
      setFeedbackBusyId(null);
    }
  }, [
    activeFilePath,
    feedbackScope,
    isChatSending,
    openFile,
    prismOptimization,
    project,
    saveActiveFile,
    sendChatMessage,
    setFeedbackError,
    setFeedbackItems,
    setFeedbackStatus,
    setSelectedPath,
    setSelectedPathType,
    workspaceId,
  ]);

  const launchDocumentOptimization = useCallback(async () => {
    const instruction = feedbackDraftComment.trim();
    const effectiveWorkspaceId = workspaceId || project?.workspace_id || "";
    if (!effectiveWorkspaceId) {
      setFeedbackError("当前 Prism 项目尚未关联 workspace，无法启动全文改稿。");
      return;
    }
    if (!project) {
      setFeedbackError("项目尚未加载完成。");
      return;
    }
    if (!activeFilePath || activeFileKind !== "text") {
      setFeedbackError("请先打开可编辑的 TeX 主稿。");
      return;
    }
    if (!instruction) {
      setFeedbackError("请先输入一句全文改稿指令。");
      return;
    }
    if (isChatSending) {
      setFeedbackError("左侧对话正在处理消息，请稍后再启动全文改稿。");
      return;
    }

    const jobId = createPrismOptimizationJobId();
    const feedbackId = `document:${jobId}`;
    setFeedbackBusyId(feedbackId);
    setFeedbackError("");
    setFeedbackStatus("正在生成全文修改建议。");
    try {
      let latexState = useLatexStore.getState();
      if (latexState.activeFileKind !== "text" || !latexState.activeFilePath) {
        throw new Error("当前文件不可执行全文改稿。");
      }
      if (latexState.activeFileContent !== latexState.activeFileSavedContent) {
        await saveActiveFile();
        latexState = useLatexStore.getState();
      }

      const filePath = latexState.activeFilePath;
      if (!filePath) {
        throw new Error("当前文件不可执行全文改稿。");
      }
      const launchContent = latexState.activeFileContent;
      if (!launchContent.trim()) {
        throw new Error("当前主稿为空，无法执行全文改稿。");
      }
      const anchor = buildFeedbackAnchor(launchContent, 0, launchContent.length);
      const job: PrismOptimizationJob = {
        id: jobId,
        feedbackId,
        status: "launching",
        filePath,
        scope: "document",
        instruction,
        selectedText: launchContent,
        createdAt: new Date().toISOString(),
      };
      prismOptimization.addJob(job);

      const prompt = [
        "请启动「Prism 全文改稿」能力（prism_selection_optimize）。",
        `目标文件：${filePath}`,
        "改稿范围：当前主稿全文",
        "用户指令：",
        instruction,
        "请结合当前主稿、工作区上下文和可用研究材料生成 Prism 待确认写入，不要直接覆盖正文。",
      ].join("\n");
      const result = await sendChatMessage(effectiveWorkspaceId, prompt, [], {
        metadata: {
          prism_selection_optimize: {
            job_id: jobId,
            feedback_id: feedbackId,
            latex_project_id: project.id,
            file_path: filePath,
          },
          orchestration: {
            params: {
              goal: "Prism 全文改稿",
              source_surface: "prism",
              rewrite_mode: "document",
              context_strategy: "workspace_manuscript_review",
              context_requirements: DOCUMENT_REWRITE_CONTEXT_REQUIREMENTS,
              latex_project_id: project.id,
              main_file: project.main_file,
              file_path: filePath,
              file_content: launchContent,
              selected_text: launchContent,
              instruction,
              comment: instruction,
              selection_start: 0,
              selection_end: launchContent.length,
              anchor,
              pdf_anchor: null,
              scope: "selection",
              feedback_id: feedbackId,
            },
          },
        },
      });

      if (result?.executionId) {
        prismOptimization.updateJob(
          jobId,
          (entry) => ({ ...entry, executionId: result.executionId ?? undefined, status: "running" }),
        );
        setFeedbackStatus("全文修改已启动，会生成待确认写入。");
        setFeedbackDraftComment("");
        return;
      }

      const detail =
        typeof result?.toolResult?.detail === "string" && result.toolResult.detail.trim()
          ? result.toolResult.detail.trim()
          : "未能生成全文修改，请稍后重试。";
      prismOptimization.updateJob(
        jobId,
        (entry) => ({
          ...entry,
          status: result?.status === "advisory" ? "advisory" : "failed",
          error: detail,
        }),
      );
      setFeedbackStatus("");
      setFeedbackError(detail);
    } catch (err) {
      const message = readClientErrorMessage(err);
      prismOptimization.updateJob(
        jobId,
        (entry) => ({
          ...entry,
          status: "failed",
          error: message,
        }),
      );
      setFeedbackStatus("");
      setFeedbackError(`启动全文改稿失败: ${message}`);
    } finally {
      setFeedbackBusyId(null);
    }
  }, [
    activeFileKind,
    activeFilePath,
    feedbackDraftComment,
    isChatSending,
    prismOptimization,
    project,
    saveActiveFile,
    sendChatMessage,
    setFeedbackError,
    setFeedbackStatus,
    workspaceId,
  ]);

  const rewriteFromFeedback = useCallback(async (item: LatexFeedbackItem) => {
    if (!project || activeFileKind !== "text") {
      setFeedbackError("当前文件不可执行点评改写。");
      return;
    }
    if (rewritePreviewFeedbackId && rewritePreviewFeedbackId !== item.id) {
      clearRewritePreview();
    }
    setFeedbackBusyId(item.id);
    setFeedbackError("");
    setFeedbackStatus("");
    try {
      const resolved = resolveFeedbackRange(item, activeFileContent);
      if (!resolved) {
        throw new Error("无法在当前文本中定位该点评原文。");
      }
      const response = await previewLatexFeedbackRewrite(project.id, {
        file_path: item.file_path,
        selected_text: resolved.text,
        comment: item.comment,
        selection_start: resolved.start,
        selection_end: resolved.end,
        anchor: item.anchor || buildFeedbackAnchor(activeFileContent, resolved.start, resolved.end),
        scope: feedbackScope,
        file_content: activeFileContent,
      });
      if (!response.candidates || response.candidates.length === 0) {
        throw new Error("模型未返回可用改写候选。");
      }
      setRewritePreviewFilePath(response.file_path);
      setRewritePreviewFeedbackId(item.id);
      setRewriteCandidates(response.candidates);
      setSelectedRewriteCandidateId(response.candidates[0].candidate_id);
      setFeedbackItems((prev) =>
        prev.map((entry) =>
          entry.id === item.id
            ? {
              ...entry,
              last_status: "pending",
              last_error: "",
            }
            : entry,
        ),
      );
      const nextStart = response.resolved_selection_start;
      const nextEnd = response.resolved_selection_end;
      if (editorRef.current) {
        editorRef.current.focus();
        editorRef.current.setSelectionRange(nextStart, nextEnd);
      }
      setSelectionRange([nextStart, nextEnd]);
      setActiveFeedbackId(item.id);
      setFeedbackStatus("已生成改写候选，请先查看 diff 并确认应用。");
    } catch (err) {
      const message = readClientErrorMessage(err);
      setFeedbackError(`点评改写失败: ${message}`);
      clearRewritePreview(false);
      setFeedbackItems((prev) =>
        prev.map((entry) =>
          entry.id === item.id
            ? { ...entry, last_status: "error", last_error: message }
            : entry,
        ),
      );
    } finally {
      setFeedbackBusyId(null);
    }
  }, [
    activeFileContent,
    activeFileKind,
    clearRewritePreview,
    editorRef,
    feedbackScope,
    project,
    rewritePreviewFeedbackId,
    setFeedbackError,
    setFeedbackItems,
    setFeedbackStatus,
    setSelectionRange,
  ]);

  const applyRewriteCandidate = useCallback(async () => {
    if (!project || !selectedRewriteCandidate || !rewritePreviewFeedbackId || !rewritePreviewFilePath) {
      return;
    }
    setIsApplyingRewrite(true);
    setFeedbackError("");
    try {
      const response = await applyLatexFeedbackRewrite(project.id, {
        file_path: rewritePreviewFilePath,
        candidate_id: selectedRewriteCandidate.candidate_id,
        candidate_signature: selectedRewriteCandidate.candidate_signature,
        target_start: selectedRewriteCandidate.target_start,
        target_end: selectedRewriteCandidate.target_end,
        rewritten_text: selectedRewriteCandidate.rewritten_text,
        base_file_hash: selectedRewriteCandidate.base_file_hash,
        base_range_hash: selectedRewriteCandidate.base_range_hash,
      });

      if (activeFilePath !== response.file_path) {
        setSelectedPath(response.file_path);
        setSelectedPathType("file");
      }
      await openFile(response.file_path);

      const nextEnd = response.target_start + response.rewritten_text.length;
      setSelectionRange([response.target_start, nextEnd]);
      if (editorRef.current) {
        editorRef.current.focus();
        editorRef.current.setSelectionRange(response.target_start, nextEnd);
      }

      setFeedbackItems((prev) =>
        shiftFeedbacksAfterRewrite(
          prev,
          response.file_path,
          rewritePreviewFeedbackId,
          response.target_start,
          response.target_end,
          response.rewritten_text,
          response.applied_content,
        ).map((entry) => (
          entry.id === rewritePreviewFeedbackId
            ? {
              ...entry,
              anchor: response.updated_anchor,
              pdf_anchor: null,
              last_status: "done",
              last_error: "",
            }
            : entry
        )),
      );
      setActiveFeedbackId(rewritePreviewFeedbackId);
      setLastRewriteUndo({
        ...response.undo,
        file_path: response.file_path,
        feedback_id: rewritePreviewFeedbackId,
      });
      setFeedbackStatus("已应用改写并写回文件。");
      clearRewritePreview(false);
    } catch (err) {
      const code = readClientErrorCode(err);
      let message = readClientErrorMessage(err);
      if (code === "rewrite_compile_failed") {
        const compileError = readClientErrorDetailField(err, "compile_error");
        message = compileError
          ? `编译校验未通过（已自动回滚）：${compileError}`
          : "编译校验未通过，系统已自动回滚。";
        setFeedbackStatus("候选未被应用，文件已自动回滚。");
      } else if (code && STRUCTURE_REWRITE_ERROR_CODES.has(code)) {
        message = "改写未通过结构安全校验，请切换候选或重新生成。";
      }
      const staleCandidate = Boolean(code && STALE_REWRITE_ERROR_CODES.has(code));
      setFeedbackError(`应用改写失败: ${message}`);
      setFeedbackItems((prev) =>
        prev.map((entry) =>
          entry.id === rewritePreviewFeedbackId
            ? { ...entry, last_status: "error", last_error: message }
            : entry,
        ),
      );
      if (staleCandidate) {
        clearRewritePreview(false);
        setFeedbackStatus("改写候选已失效，请重新生成 diff。");
      }
    } finally {
      setIsApplyingRewrite(false);
    }
  }, [
    activeFilePath,
    clearRewritePreview,
    editorRef,
    openFile,
    project,
    rewritePreviewFeedbackId,
    rewritePreviewFilePath,
    selectedRewriteCandidate,
    setFeedbackError,
    setFeedbackItems,
    setFeedbackStatus,
    setSelectedPath,
    setSelectedPathType,
    setSelectionRange,
  ]);

  const regenerateRewritePreview = useCallback(async () => {
    if (!previewFeedbackItem || feedbackBusyId || isApplyingRewrite) {
      return;
    }
    await rewriteFromFeedback(previewFeedbackItem);
  }, [feedbackBusyId, isApplyingRewrite, previewFeedbackItem, rewriteFromFeedback]);

  const copySelectedRewrite = useCallback(async () => {
    if (!selectedRewriteCandidate) {
      return;
    }
    if (!navigator?.clipboard?.writeText) {
      setFeedbackError("当前环境不支持复制到剪贴板。");
      return;
    }
    try {
      await navigator.clipboard.writeText(selectedRewriteCandidate.rewritten_text);
      setFeedbackStatus("已复制当前候选改写文本。");
    } catch {
      setFeedbackError("复制失败，请检查浏览器剪贴板权限。");
    }
  }, [selectedRewriteCandidate, setFeedbackError, setFeedbackStatus]);

  const toggleDiffHunkCollapsed = useCallback((hunkKey: string) => {
    setCollapsedDiffHunks((prev) => ({
      ...prev,
      [hunkKey]: !prev[hunkKey],
    }));
  }, []);

  const setAllDiffHunksCollapsed = useCallback((collapsed: boolean) => {
    if (!selectedRewriteCandidate) {
      return;
    }
    const next: Record<string, boolean> = {};
    selectedRewriteCandidate.diff.hunks.forEach((hunk, index) => {
      const key = `${hunk.old_start}-${hunk.old_end}-${hunk.new_start}-${hunk.new_end}-${index}`;
      next[key] = collapsed;
    });
    setCollapsedDiffHunks(next);
  }, [selectedRewriteCandidate]);

  const undoLastRewrite = useCallback(async () => {
    if (!project || !lastRewriteUndo) {
      return;
    }
    setIsApplyingRewrite(true);
    setFeedbackError("");
    try {
      const response = await revertLatexFeedbackRewrite(project.id, {
        file_path: lastRewriteUndo.file_path,
        candidate_id: lastRewriteUndo.candidate_id,
        revert_start: lastRewriteUndo.revert_start,
        revert_end: lastRewriteUndo.revert_end,
        rewritten_text: lastRewriteUndo.rewritten_text,
        previous_text: lastRewriteUndo.previous_text,
        applied_file_hash: lastRewriteUndo.applied_file_hash,
        revert_signature: lastRewriteUndo.revert_signature,
      });

      if (activeFilePath !== response.file_path) {
        setSelectedPath(response.file_path);
        setSelectedPathType("file");
      }
      await openFile(response.file_path);

      const nextEnd = response.revert_start + response.restored_text.length;
      setSelectionRange([response.revert_start, nextEnd]);
      if (editorRef.current) {
        editorRef.current.focus();
        editorRef.current.setSelectionRange(response.revert_start, nextEnd);
      }

      setFeedbackItems((prev) =>
        shiftFeedbacksAfterRewrite(
          prev,
          response.file_path,
          lastRewriteUndo.feedback_id,
          response.revert_start,
          response.revert_end,
          response.restored_text,
          response.reverted_content,
        ).map((entry) =>
          entry.id === lastRewriteUndo.feedback_id
            ? {
              ...entry,
              anchor: response.updated_anchor,
              pdf_anchor: null,
              last_status: "idle",
              last_error: "",
            }
            : entry,
        ),
      );
      setActiveFeedbackId(lastRewriteUndo.feedback_id);
      setFeedbackStatus("已撤销最近一次改写。");
      setLastRewriteUndo(null);
    } catch (err) {
      setFeedbackError(`撤销改写失败: ${readClientErrorMessage(err)}`);
    } finally {
      setIsApplyingRewrite(false);
    }
  }, [
    activeFilePath,
    editorRef,
    lastRewriteUndo,
    openFile,
    project,
    setFeedbackError,
    setFeedbackItems,
    setFeedbackStatus,
    setSelectedPath,
    setSelectedPathType,
    setSelectionRange,
  ]);

  useEffect(() => {
    if (!rewritePreviewFeedbackId || !selectedRewriteCandidate) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "enter") {
        if (!isApplyingRewrite && activeFileContent === activeFileSavedContent) {
          event.preventDefault();
          void applyRewriteCandidate();
        }
        return;
      }
      if (event.key === "Escape" && !isApplyingRewrite) {
        event.preventDefault();
        clearRewritePreview();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [
    activeFileContent,
    activeFileSavedContent,
    applyRewriteCandidate,
    clearRewritePreview,
    isApplyingRewrite,
    rewritePreviewFeedbackId,
    selectedRewriteCandidate,
  ]);

  const addFeedbackAndRewrite = useCallback(async () => {
    const item = await createFeedbackFromSelection(true);
    if (!item) {
      return;
    }
    setFeedbackItems((prev) => [...prev, item]);
    setActiveFeedbackId(item.id);
    setFeedbackDraftComment("");
    setPdfDraftSelection(null);
    await launchPrismOptimizationFromFeedback(item);
  }, [
    createFeedbackFromSelection,
    launchPrismOptimizationFromFeedback,
    setFeedbackItems,
    setPdfDraftSelection,
  ]);

  const addFeedbackAndQuickRewrite = useCallback(async () => {
    const item = await createFeedbackFromSelection(true);
    if (!item) {
      return;
    }
    setFeedbackItems((prev) => [...prev, item]);
    setActiveFeedbackId(item.id);
    setFeedbackDraftComment("");
    setPdfDraftSelection(null);
    await rewriteFromFeedback(item);
  }, [
    createFeedbackFromSelection,
    rewriteFromFeedback,
    setFeedbackItems,
    setPdfDraftSelection,
  ]);

  const protectActiveFile = useCallback(async () => {
    if (!project || !activeFilePath || activeFileKind !== "text") {
      return;
    }
    setIsProtectingActiveFile(true);
    setProtectionStatus("");
    setProtectionError("");
    try {
      await protectLatexSection(project.id, {
        path: activeFilePath,
        scope: "file",
        reason: "user_manual_protect",
      });
      onReviewStateChanged?.();
      setProtectionStatus("当前文件已保护，后续 agent 会以建议形式处理改写。");
    } catch (err) {
      setProtectionError(`保护当前文件失败: ${readClientErrorMessage(err)}`);
    } finally {
      setIsProtectingActiveFile(false);
    }
  }, [activeFileKind, activeFilePath, onReviewStateChanged, project]);

  return {
    selectionText,
    hasFeedbackSelection,
    pdfHighlightFeedbacks,
    view: {
      feedbackDraftComment,
      feedbackScope,
      canCreateFeedback,
      feedbackContextText,
      feedbackBusyId,
      protectionStatus,
      protectionError,
      isProtectingActiveFile,
      activeFeedbackId,
      lastRewriteUndo,
      isApplyingRewrite,
      selectedRewriteCandidate,
      selectedRewriteCandidateIndex,
      rewriteCandidates,
      diffViewMode,
      showWhitespaceOnlyDiff,
      collapsedDiffHunks,
      previewFeedbackItem,
      currentFileFeedbacks,
    },
    actions: {
      setFeedbackDraftComment,
      setFeedbackScope,
      addFeedbackAndQuickRewrite,
      addFeedbackAndRewrite,
      launchDocumentOptimization,
      addFeedbackOnly,
      protectFile: protectActiveFile,
      undoRewrite: undoLastRewrite,
      selectRewriteCandidate: setSelectedRewriteCandidateId,
      regenerateRewrite: regenerateRewritePreview,
      setDiffViewMode,
      toggleWhitespaceOnlyDiff: () => setShowWhitespaceOnlyDiff((prev) => !prev),
      setAllDiffHunksCollapsed,
      toggleDiffHunkCollapsed,
      copySelectedRewrite,
      cancelRewritePreview: () => clearRewritePreview(),
      applyRewrite: applyRewriteCandidate,
      focusFeedback,
      rewrite: rewriteFromFeedback,
      launchPrismOptimization: launchPrismOptimizationFromFeedback,
      removeFeedback,
    },
  };
}
